import boto3


# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
slots_table = dynamodb.Table("Slots")
appointments_table = dynamodb.Table("Appointments")
