from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, render_template, Response, session
from openai import OpenAI
import os
from functools import wraps
import logging
import datetime

# Initialize app + session key
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Basic auth credentials
USERNAME = os.getenv("APP_USERNAME")
PASSWORD = os.getenv("APP_PASSWORD")


# IP usage limit
IP_USAGE = {}

def too_many_prompts(ip):
    IP_USAGE[ip] = IP_USAGE.get(ip, 0) + 1
    return IP_USAGE[ip] > 5

# Logging
logging.basicConfig(
    filename='logs/prompts.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# Auth helpers
def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def authenticate():
    return Response('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# Prompt templates
PROMPT_TEMPLATES = {
    "scope": "You are a construction project manager. Create a detailed scope of work for: {input}",
    "quote": "You are a contractor. Write a professional quote based on: {input}",
    "post": "You are a blue-collar influencer. Write a confident, short Instagram post about: {input}"
}

VALID_CLASSES = {
    "Scope of Work": "scope",
    "Quote": "quote",
    "Social Media Post": "post"
}

@app.route("/", methods=["GET"])
@requires_auth
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
@requires_auth
def generate():
    user_input = request.form["user_input"]
    user_ip = request.remote_addr

    print("User input:", user_input)

    if too_many_prompts(user_ip):
        return render_template("result.html", output="Limit reached. Please sign up to continue.")

    session["prompt_count"] = session.get("prompt_count", 0) + 1
    print(f"Prompt count this session: {session['prompt_count']}")

    # Log prompt
    timestamp = datetime.datetime.now().isoformat()
    with open("prompt_logs.txt", "a") as f:
        f.write(f"[{timestamp}] IP: {user_ip} | Prompt: {user_input}\n")
    logging.info(f"Raw input: {user_input}")

    # Classification
    classification_prompt = f"""
Classify the following input into one of the following categories:
- Scope of Work
- Quote
- Social Media Post

Only return the category name exactly.

Input: {user_input}
"""
    try:
        classification_response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": classification_prompt}]
        )
        classification = classification_response.choices[0].message.content.strip()
        print(f"🧠 Classification: {classification}")
    except Exception as e:
        return render_template("result.html", output=f"Classification error: {str(e)}")

    prompt_key = VALID_CLASSES.get(classification)
    if not prompt_key:
        logging.warning(f"Invalid classification returned: '{classification}'")
        return render_template("result.html", output="Sorry, I couldn't classify your input.")

    logging.info(f"Classified as: {classification} → Using prompt: {prompt_key}")
    system_prompt = PROMPT_TEMPLATES[prompt_key].format(input=user_input)

    # DEBUGGING
    print("Prompt key:", prompt_key)
    print("System prompt:", system_prompt)

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": system_prompt}]
            max_tokens=500
        )
        result = response.choices[0].message.content.strip()
    except Exception as e:
        result = f"Error: {str(e)}"

    logging.info(f"Output generated: {result[:100]}...")
    return render_template("result.html", output=result)


    

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # 5000 for local fallback
    app.run(host="0.0.0.0", port=port)
