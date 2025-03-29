from flask import Flask, request, jsonify, send_file
from PIL import Image
from pyzbar.pyzbar import decode as pyzbar_decode
import zlib
import base64
import io

app = Flask(__name__)

def decode_secure_qr(qr_str):
    """
    Decodes a UIDAI secure QR code from a base10-encoded string (skipping signature verification).
    Steps:
      1. Convert the base10 string to an integer, then to a byte array.
      2. Decompress the byte array using zlib.
      3. Extract 16 text fields (delimited by byte value 255) using ISO-8859-1 encoding.
      4. Determine tail length (256 bytes signature + optional mobile/email fields based on the indicator).
      5. Extract photo bytes (between last text delimiter and start of tail) and encode in base64.
      6. Extract mobile/email fields (if present) by reversing their fixed-size byte order and converting to hex.
    Returns a dictionary with the decoded fields.
    """
    try:
        big_int = int(qr_str)
        nbytes = (big_int.bit_length() + 7) // 8
        data_bytes = big_int.to_bytes(nbytes, 'big')
    except Exception as e:
        raise Exception("Error converting QR data to bytes: " + str(e))
    
    try:
        decompressed = zlib.decompress(data_bytes)
    except Exception as e:
        raise Exception("Decompression failed: " + str(e))
    
    delimiter = 255
    delimiter_positions = []
    for i, b in enumerate(decompressed):
        if b == delimiter:
            delimiter_positions.append(i)
            if len(delimiter_positions) == 16:
                break
    if len(delimiter_positions) < 16:
        raise Exception("Not enough delimiters found; expected 16 text fields.")
    
    text_fields = []
    start = 0
    for pos in delimiter_positions:
        try:
            field = decompressed[start:pos].decode("ISO-8859-1")
        except Exception as e:
            raise Exception("Error decoding text field: " + str(e))
        text_fields.append(field)
        start = pos + 1

    keys = [
        "indicator", "referenceId", "name", "dob", "gender",
        "care_of", "district", "landmark", "house", "location",
        "pin_code", "post_office", "state", "street", "sub_district", "VTC"
    ]
    if len(text_fields) != len(keys):
        raise Exception("Unexpected number of text fields extracted.")
    
    text_data = dict(zip(keys, text_fields))
    
    try:
        indicator = int(text_data["indicator"])
    except Exception as e:
        raise Exception("Invalid indicator value: " + str(e))
    
    tail_extra = 0
    if indicator == 3:
        tail_extra = 64  # Both mobile and email present (32 bytes each)
    elif indicator in [1, 2]:
        tail_extra = 32  # Only one present
    
    tail_length = 256 + tail_extra
    tail_start = len(decompressed) - tail_length

    photo_bytes = decompressed[delimiter_positions[-1] + 1 : tail_start]
    photo_b64 = base64.b64encode(photo_bytes).decode('utf-8')

    mobile = None
    email = None
    if indicator == 3:
        mobile_bytes = decompressed[tail_start : tail_start + 32]
        email_bytes = decompressed[tail_start + 32 : tail_start + 64]
        mobile = mobile_bytes[::-1].hex()
        email = email_bytes[::-1].hex()
    elif indicator == 1:
        mobile_bytes = decompressed[tail_start : tail_start + 32]
        mobile = mobile_bytes[::-1].hex()
    elif indicator == 2:
        email_bytes = decompressed[tail_start : tail_start + 32]
        email = email_bytes[::-1].hex()
    
    result = text_data.copy()
    result["photo"] = photo_b64
    if mobile:
        result["mobile"] = mobile
    if email:
        result["email"] = email

    return result

@app.route('/upload', methods=['POST'])
def upload_qr():
    """
    Expects a multipart/form-data POST with file field 'qr_image'.
    Uses pyzbar to decode the QR image (which contains a very large base10 string),
    then decodes it using the UIDAI secure QR code steps (signature verification is skipped).
    Returns the decoded data in JSON.
    """
    if 'qr_image' not in request.files:
        return jsonify({"error": "No QR image provided"}), 400
    file = request.files['qr_image']
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        image = Image.open(file.stream)
    except Exception as e:
        return jsonify({"error": "Error opening image: " + str(e)}), 400

    decoded_objs = pyzbar_decode(image)
    if not decoded_objs:
        return jsonify({"error": "No QR code detected or unable to decode"}), 400

    qr_data = decoded_objs[0].data.decode("utf-8", errors="replace")
    if not qr_data:
        return jsonify({"error": "QR code data is empty"}), 400

    try:
        decoded = decode_secure_qr(qr_data)
        return jsonify({"decoded_data": decoded})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    # For deployment on Render or Vercel, ensure the web server runs on the port provided by the environment.
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
