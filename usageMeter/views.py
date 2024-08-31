import os
import google.generativeai as genai
import json
from uuid import uuid1
from io import BytesIO

from PIL import Image
from django.db.models.functions import Trunc

from django.http import HttpResponse
from dotenv import load_dotenv

from usageMeter.models import Measurement
from usageMeter.utils import decode_image, get_json, return_status_400

# Load API key from .env
load_dotenv()

genai.configure(api_key=os.getenv('GEMINI_API_KEY'))


def index(request):
    return HttpResponse("Make a POST request to /upload/ to get started.")


def upload(request):
    # Make sure the request is "POST"
    if request.method == "POST":
        try:
            # Get the JSON from request.body
            params = get_json(request.body)

            # Decode the base64 string into a binary image
            image_binary = decode_image(params["image"])

            # Store the remaining params in variables
            customer_code = params["customer_code"]
            measure_datetime = params["measure_datetime"]

            # Ensure the measurement hasn't been taken for the month
            if measure_datetime[0:7] in Measurement.objects.all().values(
                    'measure_datetime')[0:7]:
                res = {
                    "error_code": "DOUBLE_REPORT",
                    "error_description": "Reading has already been taken for the month."
                }

                return HttpResponse(res, 409)

            measure_type = params["measure_type"]

            # Make sure the data types are correct
            for obj in (customer_code, measure_datetime, measure_type):
                assert isinstance(obj, str), "Invalid type: Not a String"

            # Make sure the measurement type is either "WATER" or "GAS"
            if str.upper(measure_type) not in ["WATER", "GAS"]:
                raise Exception("Measurement type not allowed. Must be either WATER or GAS.")
        except Exception as e:
            # Return any errors
            res = {
                "error_code": "INVALID_DATA",
                "error_description": f"The data provided in the body of the request is invalid: {e}",
            }

            return return_status_400(res)

        try:
            # Save the image binary to a variable
            image_file = Image.open(BytesIO(image_binary))

            # Save the image to a file
            # (This is necessary because the Gemini API stupidly doesn't support getting a URI from an inline image)
            # Also converts the image format to lossless png
            image_file.save("image.png")

            # Upload image to Gemini
            image = genai.upload_file(path="image.png")

        except Exception as e:
            # Display any errors with converting to an image
            res = {
                "error_code": "INVALID_IMAGE",
                "error_description": f"The base64 string provided could not be converted to an image: {e}",
            }

            return return_status_400(res)

        # Select a Gemini model, changing it to Pro crashes the server for some reason
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")

        # Prompt the model with text and the previously uploaded image.
        result = model.generate_content(
            [image, "Can you tell me what the reading on this meter says? Output just a number and nothing else."]).text

        try:
            measure_value = int(result)
        except Exception as e:
            res = {
                "error_code": "INVALID_RESULT",
                "error_description": f"The data returned from the model did not resolve to a single integer value: {e}",
            }

            return return_status_400(res)

        # Generate a new UUID
        measure_uuid = uuid1()

        # Attempt to add measurement to the database
        try:
            measurement = Measurement(image_url=image.uri, customer_code=customer_code,
                                      measure_datetime=measure_datetime,
                                      measure_type=measure_type, measure_value=measure_value, measure_uuid=measure_uuid)

            measurement.save()
        except Exception as e:
            # Catch any errors
            res = {
                "error_code": "INVALID_DATA",
                "error_description": f"The measurement couldn't be added to the database.: {e}",
            }

            return return_status_400(res)

        # If successful, return the answer in JSON format
        res = {
            "image_url": image.uri,
            "measure_value": measure_value,
            "measure_uuid": measure_uuid.__str__()
        }

        return HttpResponse(json.dumps(res))

    # Prevent the server from crashing if someone doesn't use POST
    return HttpResponse("This route only supports post requests.")
