from django.db import models


# Create your models here.

class Measurement(models.Model):
    image_url = models.CharField(max_length=64)
    customer_code = models.CharField(max_length=64)
    measure_datetime = models.DateTimeField()
    measure_type = models.CharField(max_length=64)
    measure_value = models.IntegerField()
    measure_uuid = models.UUIDField()
