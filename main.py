
from flask import Flask, request, jsonify, send_file
from PIL import Image
from pathlib import Path
import io
import struct
import zlib
import json
import secrets
import math
import time

# ==========================================
# UNO Q IMAGE COMPRESSION SERVER
# ==========================================

app = Flask(__name__)

STORAGE = Path.home() / "image_transfer"
STORAGE.mkdir(parents=True, exist_ok=True)

MAX_WIDTH = 160
MAX_HEIGHT = 120

JPEG_QUALITY = 45
PACKET_SIZE = 48

MAGIC = b"\xA5\x5A"

# Packet header excluding CRC
HEADER_FORMAT = "<2sIHHHI"

# 16 bytes
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# Header + CRC
PACKET_HEADER_SIZE = HEADER_SIZE + 4


# ==========================================
# IMAGE COMPRESSION
# ==========================================

def compress_image(image_bytes):

    image = Image.open(io.BytesIO(image_bytes))

    image = image.convert("RGB")

    image.thumbnail((MAX_WIDTH, MAX_HEIGHT))

    output = io.BytesIO()

    image.save(
        output,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True
    )

    compressed = output.getvalue()

    return compressed, image.size


# ==========================================
# PACKET GENERATOR
# ==========================================

def generate_packets(jpeg_data, image_id):

    packets = []

    total_size = len(jpeg_data)

    total_packets = math.ceil(
        total_size / PACKET_SIZE
    )

    for index in range(total_packets):

        start = index * PACKET_SIZE

        payload = jpeg_data[
            start:start + PACKET_SIZE
        ]

        header = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            image_id,
            index,
            total_packets,
            len(payload),
            total_size
        )

        checksum = zlib.crc32(
            header + payload
        ) & 0xFFFFFFFF

        packet = (
            header
            + struct.pack("<I", checksum)
            + payload
        )

        packets.append(packet)

    return packets


# ==========================================
# SAVE PACKETS AS A BINARY FILE
# ==========================================

def save_packets(packets):

    packet_path = STORAGE / "packets.bin"

    with open(packet_path, "wb") as file:

        for packet in packets:

            # 2-byte length prefix
            file.write(
                struct.pack("<H", len(packet))
            )

            file.write(packet)

    return packet_path


# ==========================================
# UPLOAD IMAGE
# ==========================================

@app.route("/upload", methods=["POST"])
def upload_image():

    try:

        original_bytes = request.get_data()

        if not original_bytes:
            return jsonify({
                "error": "Empty image"
            }), 400

        if len(original_bytes) > 20_000_000:
            return jsonify({
                "error": "Image too large"
            }), 413

        # Validate and compress
        jpeg_data, resolution = compress_image(
            original_bytes
        )

        image_id = secrets.randbits(32)

        # Save compressed image
        compressed_path = STORAGE / "compressed.jpg"

        compressed_path.write_bytes(jpeg_data)

        # Generate packets
        packets = generate_packets(
            jpeg_data,
            image_id
        )

        # Store binary packets
        packet_path = save_packets(packets)

        # Metadata
        metadata = {

            "image_id": image_id,

            "original_upload_size": len(original_bytes),

            "compressed_size": len(jpeg_data),

            "width": resolution[0],

            "height": resolution[1],

            "jpeg_quality": JPEG_QUALITY,

            "packet_size": PACKET_SIZE,

            "total_packets": len(packets),

            "packet_header_size": PACKET_HEADER_SIZE,

            "protocol": "UNOQ-IMG-V1",

            "created": time.time()
        }

        metadata_path = STORAGE / "metadata.json"

        metadata_path.write_text(
            json.dumps(metadata, indent=4)
        )

        print("\nIMAGE PROCESSED")
        print("--------------------------")
        print("Original:", len(original_bytes))
        print("Compressed:", len(jpeg_data))
        print("Resolution:", resolution)
        print("Packets:", len(packets))
        print("Image ID:", image_id)
        print("--------------------------")

        return jsonify(metadata)

    except Exception as error:

        print("ERROR:", error)

        return jsonify({
            "error": str(error)
        }), 400


# ==========================================
# DOWNLOAD PACKET FILE
# ==========================================

@app.route("/download/packets")
def download_packets():

    path = STORAGE / "packets.bin"

    if not path.exists():
        return jsonify({"error": "No packets available"}), 404

    return send_file(
        path,
        as_attachment=True,
        download_name="packets.bin"
    )


# ==========================================
# DOWNLOAD METADATA
# ==========================================

@app.route("/download/metadata")
def download_metadata():

    path = STORAGE / "metadata.json"

    if not path.exists():
        return jsonify({"error": "No metadata"}), 404

    return send_file(
        path,
        as_attachment=True,
        download_name="metadata.json"
    )


# ==========================================
# DOWNLOAD COMPRESSED JPEG FOR COMPARISON
# ==========================================

@app.route("/download/compressed")
def download_compressed():

    path = STORAGE / "compressed.jpg"

    if not path.exists():
        return jsonify({"error": "No image"}), 404

    return send_file(
        path,
        as_attachment=True,
        download_name="compressed.jpg"
    )


# ==========================================
# SERVER STATUS
# ==========================================

@app.route("/")
def home():

    return jsonify({
        "device": "Arduino UNO Q",
        "service": "Image Compression and Packet Server",
        "status": "Running"
    })


# ==========================================
# START SERVER
# ==========================================

if __name__ == "__main__":

    print("UNO Q IMAGE SERVER STARTING")

    print("Storage:", STORAGE)

    app.run(
        host="0.0.0.0",
        port=5001,
        debug=False,
        threaded=True
    )
