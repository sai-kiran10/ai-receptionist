import os
import boto3
from dotenv import load_dotenv

load_dotenv()

#Extraxt credentials from .env file
aws_access_key = os.getenv("AWS_ACCESS_ID")
aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_region = os.getenv("AWS_REGION", "us-east-1")

print(f"🚀 DEBUG: Manual Auth Init - Region: {aws_region}")

dynamodb = boto3.resource(
    'dynamodb',
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
    region_name=aws_region
)

#Initialize resources and clients using the session
slots_table = dynamodb.Table("Slots") 
appointments_table = dynamodb.Table("Appointments")