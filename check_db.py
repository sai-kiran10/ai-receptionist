from app.db import slots_table

def check_data():
    print("Checking DynamoDB for slots...")
    response = slots_table.scan()
    items = response.get('Items', [])
    
    if items:
        print(f"✅ Found {len(items)} slots. First item looks like this:")
        # Print the whole first item to see all key names
        print(items[0]) 
    else:
        print("❌ Table is empty.")

if __name__ == "__main__":
    check_data()