from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, render_template, Response, session
import openai
import os
from functools import wraps
import logging
import datetime

# 🔧 Initialize app + secret key first
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# ✅ Check env vars early
USERNAME = os.getenv("APP_USERNAME")
PASSWORD = os.getenv("APP_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

print("USERNAME:", USERNAME)
print("PASSWORD:", PASSWORD)
print("OPENAI_API_KEY loaded:", bool(OPENAI_API_KEY))

# ✅ Configure OpenAI (new style for v1+)
openai.api_key = OPENAI_API_KEY

IP_USAGE = {}

def too_many_prompts(ip):
    IP_USAGE[ip] = IP_USAGE.get(ip, 0) + 1
    return IP_USAGE[ip] > 5

# 🔐 Basic auth helpers
def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def authenticate():
    return Response('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            print("Auth failed:", auth)
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# 🎯 Prompt templates
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

# 🪵 Logging setup
logging.basicConfig(
    filename='logs/prompts.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

@app.route("/", methods=["GET"])
@requires_auth
def index():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
@requires_auth
def generate():
    user_input = request.form["user_input"]
    user_ip = request.remote_addr

    if too_many_prompts(user_ip):
        return render_template("result.html", output="Limit reached. Please sign up to continue.")

    session["prompt_count"] = session.get("prompt_count", 0) + 1
    print(f"Prompt count this session: {session['prompt_count']}")

    timestamp = datetime.datetime.now().isoformat()
    with open("prompt_logs.txt", "a") as f:
        f.write(f"[{timestamp}] IP: {user_ip} | Prompt: {user_input}\n")

    logging.info(f"Raw input: {user_input}")

    # 🔍 Step 1: Classification
    classification_prompt = f"""
Classify the following input into one of the following categories:
- Scope of Work
- Quote
- Social Media Post

Only return the category name exactly.

Input: {user_input}
"""

    try:
        classification_response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": classification_prompt}]
        )
        classification = classification_response.choices[0].message.content.strip()
    except openai.APIError as e:
        logging.error(f"OpenAI classification error: {e}")
        return render_template("result.html", output="Error classifying your input.")
    except Exception as e:
        return render_template("result.html", output=f"Error: {e}")

    prompt_key = VALID_CLASSES.get(classification)
    logging.info(f"Classified as: {classification} → Using prompt: {prompt_key}")

    if not prompt_key:
        return render_template("result.html", output="Sorry, I couldn't classify your input.")

    system_prompt = PROMPT_TEMPLATES[prompt_key].format(input=user_input)

    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": system_prompt}]
        )
        result = response.choices[0].message.content.strip()
    except openai.RateLimitError:
        result = "Quota exceeded. Check your OpenAI usage or billing settings."
    except Exception as e:
        result = f"Error generating output: {e}"

    logging.info(f"Output generated: {result[:100]}...")
    return render_template("result.html", output=result)


if __name__ == "__main__":
  import os
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)

