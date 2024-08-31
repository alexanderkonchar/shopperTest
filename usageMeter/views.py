import os
import google.generativeai as genai
import json
from uuid import uuid1
from io import BytesIO

from PIL import Image
from django.contrib.messages import success
from django.db.models.functions import Trunc

from django.http import HttpResponse
from dotenv import load_dotenv

from usageMeter.models import Measurement
from usageMeter.utils import decode_image, get_json, return_status_400

# Load API key from .env
load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))


def index(request):
    return HttpResponse("Make a POST request to upload/ to get started.")


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
            measure_type = str.upper(params["measure_type"])

            # Ensure the measurement hasn't been taken for the month
            if measure_datetime[0:7] in Measurement.objects.all().values(
                    'measure_datetime')[0:7]:
                res = {
                    "error_code": "DOUBLE_REPORT",
                    "error_description": "Reading has already been taken for the month."
                }

                return HttpResponse(res, 409)

            # Make sure the data types are correct
            for obj in (customer_code, measure_datetime, measure_type):
                assert isinstance(obj, str), "Invalid type: Not a String"

            # Make sure the measurement type is either "WATER" or "GAS"
            if measure_type not in ["WATER", "GAS"]:
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

        # Select a Gemini model (Changing it to Pro crashes the server for some reason)
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")

        # Prompt the model with text and the previously uploaded image
        result = model.generate_content(
            [image, "Can you tell me what the reading on this meter says? Output just a number and nothing else."]).text

        # Get the result as an integer
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

    else:
        # Prevent the server from crashing if someone doesn't use POST
        return HttpResponse("This route only supports POST requests.")


def confirm(request):
    if request.method == "PATCH":
        try:
            # Get the JSON from request.body
            params = get_json(request.body)

            # Store the params in variables
            measure_uuid = params["measure_uuid"]
            confirmed_value = params["confirmed_value"]

            assert isinstance(measure_uuid, str), "Invalid type: measure_uuid is not a String"
            assert isinstance(confirmed_value, int), "Invalid type: confirmed_value is not an Integer"

        except Exception as e:
            # Return any errors
            res = {
                "error_code": "INVALID_DATA",
                "error_description": f"The data provided in the body of the request is invalid: {e}",
            }

            return return_status_400(res)

        measurement = Measurement.objects.get(measure_uuid=measure_uuid)

        if not measurement:
            res = {
                "error_code":
                    "MEASURE_NOT_FOUND",
                "error_description": f"No results matching uuid {measure_uuid} found in the database."
            }

            return HttpResponse(json.dumps(res), status=404)

        if measurement.has_confirmed:
            res = {
                "error_code":
                    "CONFIRMATION_DUPLICATE",
                "error_description": "Reading already confirmed"
            }

            return HttpResponse(json.dumps(res), status=409)

        if measurement.measure_value == confirmed_value:
            measurement.has_confirmed = True
            measurement.save()

        else:
            measurement.measure_value = confirmed_value
            measurement.save()

        res = {
            "success": True
        }

        return HttpResponse(json.dumps(res))
    else:
        # Prevent the server from crashing if someone doesn't use PATCH
        return HttpResponse("This route only supports PATCH requests.")


def list_measurements(request, customer_code):
    # Get the optional url parameter
    measure_type = request.GET.get('measure_type')

    # If measure_type provided, ensure it's either "WATER or "GAS
    if measure_type:
        if str.upper(measure_type) not in ["WATER", "GAS"]:
            res = {
                "error_code": "INVALID_TYPE",
                "error_description": "Measurement type not allowed"
            }

            return return_status_400(res)

        # Get the measurements
        measurements = Measurement.objects.filter(customer_code=customer_code, measure_type=measure_type)
    else:
        measurements = Measurement.objects.filter(customer_code=customer_code)

    # Initialize response to be filled in with list of measurements
    res = {
        "customer_code": customer_code,
        "measures": []
    }

    # Fill in list of measurements with JSON
    for measurement in measurements:
        res["measures"] += {
            "measure_uuid": measurement.measure_uuid.__str__(),
            "measure_datetime": measurement.measure_datetime.__str__(),
            "measure_type": measurement.measure_type,
            "has_confirmed": measurement.has_confirmed,
            "image_url": measurement.image_url
        },

    # If there's no list, send a different response
    if measurements.count() == 0:
        res = {
            "error_code": "MEASURES_NOT_FOUND",
            "error_description": "No reading found"
        }

        return HttpResponse(json.dumps(res), status=404)

    return HttpResponse(json.dumps(res))
