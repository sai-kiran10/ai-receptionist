from app.db import slots_table, sns_client

def test_connection():
    try:
        # Check DynamoDB
        count = slots_table.item_count
        print(f"✅ DynamoDB Connected! (Current slot count: {count})")
        
        # Check SNS
        sns_client.get_sms_attributes()
        print("✅ AWS SNS Connected!")
        
    except Exception as e:
        print(f"❌ Connection Failed: {e}")

if __name__ == "__main__":
    test_connection()