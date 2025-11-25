from datetime import datetime
import os
import telebot
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pymongo import MongoClient

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
API_KEY = os.getenv('AI_API_KEY')
connection_string = os.getenv('MONGODB_URI')
ALLOWED_ID = os.getenv('ALLOWED_USER_ID')

prompt = (f"You are an expert event manager and I need your help to convert the below message into an argument and map it to a specific function for me"
          f"remove any typos and neatly format me the required message."
          f"If the year is not specified in the message then assume it is the {datetime.now().year}")

try:
    client = MongoClient(connection_string)
    client.admin.command("ping")
    print("Successfully connected")

except Exception as e:
    print("Connection failed:", e)

database = client["events"]
collection = database["events"]

bot = telebot.TeleBot(BOT_TOKEN)

# Function declarations
# Get all updates
get_events_function = {
    "name": "get_all_events",
    "description": "Fetches all the updates in the database",
    "parameters": {
        "type": "object",
        "properties": {

        },
    },
}

# Add updates
add_event_function = {
    "name": "add_event",
    "description": "Adds a specific event to the database",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the upcoming event",
            },
            "date": {
                "type": "string",
                "description": "Date of the upcoming event (e.g., '2025-12-13')",
            },
        },
        "required": ["name", "date"],
    },
}

# Add updates
update_event_function = {
    "name": "update_event",
    "description": "Updates a specific event based on the name to the database",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the event",
            },
            "date": {
                "type": "string",
                "description": "Updated date of the event (e.g., '2025-12-13')",
            },
        },
        "required": ["name", "date"],
    },
}

# Get events before a specific date
get_datewise_event_function = {
    "name": "get_datewise_event",
    "description": "Fetches all events before a specific date",
    "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Date before which all events are required (e.g., '2024-07-29')",
            },
        },
        "required": ["date"],
    },
}

# Get a specific event based on name
get_specific_event_function = {
    "name": "get_specific_event",
    "description": "Fetches date for a specific event.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the required event",
            },
        },
        "required": ["name"],
    },
}

client = genai.Client(api_key=API_KEY)
tools = types.Tool(function_declarations=[get_events_function,add_event_function,get_specific_event_function])
config = types.GenerateContentConfig(tools=[tools])

@bot.message_handler(commands=['start','hello'])
def send_welcome(message):
    bot.reply_to(message,"Hello how can I help you")

@bot.message_handler(commands=['help'])
def send_help(message):
    text=("The Event Manager help you to get instant updates about upcoming exams, events and any important notifications. Talk in natural language to get upcoming events"
          "if not admin, you cannot add/delete updates but you can query for updates.\n"
          "Available commands:\n/hello: To say hello.\n/thanks: To say thanks.")
    bot.reply_to(message,text)

@bot.message_handler(commands=['thanks','thank you'])
def send_welcome(message):
    bot.reply_to(message,"Happy to help.")

@bot.message_handler(commands=['delete'])
def delete_event(message):
    """Deleting updates to the database."""
    today = datetime.today()
    if (str(message.from_user.id) == ALLOWED_ID):
        collection.delete_many({"date" :{"$lte":today}})
        res_msg="Events deleted successfully."
    else:
        res_msg = "You are not authorised to delete updates"
    bot.send_message(message.chat.id, res_msg, parse_mode="Markdown")

# Main Functions
def get_all_events()->str:
    """Fetches all the upcoming updates"""
    data = collection.find()
    documents = list(data)
    res = []
    for document in documents:
        date = document["date"].strftime("%d/%m/%Y")
        res.append(f"Event: {document["name"]} | Date: {date}")
    response = "\n".join(res)
    return response

def add_event(args:object)->str:
    data = dict()
    data['name'] = args['name']
    data['date'] = datetime.strptime(args['date'], "%Y-%m-%d")
    result = collection.insert_one(data)
    final_message="Event added successfully"
    return final_message

def update_event(args:object)->str:
    collection.update_one(
        {"name": args['name']},
        {"$set": {"date": args['date']}}
    )
    final_message="Event updated successfully"

def get_datewise_event(args:object)->str:
    """Getting updates based on a specific date."""
    today = datetime.today()
    date = datetime.strptime(args['date'],"%Y-%m-%d")
    if date < today:
        return "Invalid date was entered."
    data = collection.find({ "date": { "$lte":date } })
    documents = list(data)
    res = []
    for document in documents:
        date = document["date"].strftime("%d/%m/%Y")
        res.append(f"Event: {document["name"]} | Date: {date}")
    response = "\n".join(res)
    return response

def get_specific_event(args:object)->str:
    """Adding updates to the database."""
    data = collection.find({'name':args['name']})
    if not data:
        return "Event not found."
    documents = list(data)
    res = []
    for document in documents:
        date = document["date"].strftime("%d/%m/%Y")
        res.append(f"Date: {date}")
    response = "\n".join(res)
    return response

@bot.message_handler(func=lambda msg:True)
def message_handle(message):
    contents = [
        types.Content(
            role="user", parts=[types.Part(text=f"{prompt} message:{message.text}")]
        )
    ]
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config = config,
    )

    tool_call = response.candidates[0].content.parts[0].function_call
    if not tool_call:
        res_msg = "I am not sure if I can do that. Type /help to explore more"
        bot.send_message(message.chat.id, res_msg, parse_mode="Markdown")
    elif tool_call.name == 'add_event':
        fun_args = response.candidates[0].content.parts[0].function_call.args
        if(str(message.from_user.id)==ALLOWED_ID):
            res_msg = add_event(fun_args)
        else:
            res_msg = "You are not authorised to add updates"
        bot.send_message(message.chat.id, res_msg, parse_mode="Markdown")
    elif tool_call.name == 'get_all_events':
        confirm = "Fetching all events..."
        bot.send_message(message.chat.id, confirm, parse_mode="Markdown")
        res_msg = get_all_events()
        bot.send_message(message.chat.id,res_msg,parse_mode="Markdown")
    elif tool_call.name == 'get_datewise_events':
        fun_args = response.candidates[0].content.parts[0].function_call.args
        confirm = f"Fetching all events before {fun_args['date']}"
        bot.send_message(message.chat.id, confirm, parse_mode="Markdown")
        res_msg = get_datewise_event(fun_args)
        bot.send_message(message.chat.id, res_msg, parse_mode="Markdown")
    elif tool_call.name == 'get_specific_event':
        fun_args = response.candidates[0].content.parts[0].function_call.args
        confirm = f"Fetching date for {fun_args['name']}"
        bot.send_message(message.chat.id, confirm, parse_mode="Markdown")
        res_msg = get_specific_event(fun_args)
        bot.send_message(message.chat.id, res_msg, parse_mode="Markdown")

bot.infinity_polling()