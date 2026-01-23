'''import boto3
# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
slots_table = dynamodb.Table("Slots")
appointments_table = dynamodb.Table("Appointments")
'''

import os
import boto3
from dotenv import load_dotenv

load_dotenv()

# Extract credentials from environment variables
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

session = boto3.Session(
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

# Initialize resources and clients using the session
dynamodb = session.resource('dynamodb')
#sns_client = session.client('sns')

slots_table = dynamodb.Table("Slots")
appointments_table = dynamodb.Table("Appointments")