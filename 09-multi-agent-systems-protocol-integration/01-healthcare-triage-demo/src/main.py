import json
import logging
import os
import re
import time
from datetime import datetime

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models import BedrockModel

load_dotenv()

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

PATIENT_COMPLAINTS = [
    {
        "patient_id": "P-1001",
        "name": "Alice Johnson",
        "complaint": "I've been having sharp chest pain for the past 2 hours,",
        "symptoms": "along with shortness of breath and dizziness.",
        "age": 58,
    },
    {
        "patient_id": "P-1002",
        "name": "Bob Smith",
        "complaint": "I have a mild headache and a runny nose that started yesterday.",
        "symptoms": "No fever.",
        "age": 32,
    },
    {
        "patient_id": "P-1003",
        "name": "Carol Davis",
        "complaint": "My ankle is swollen and painful after I twisted it while jogging",
        "symptoms": "this morning. I can still put some weight on it.",
        "age": 27,
    },
]

AVAILABLE_SLOTS = {
    "urgent": ["00:00 AM (Emergency)", "00:15 AM (Emergency)"],
    "standard": ["10:30 AM", "11:00 AM", "11:30 AM"],
    "routine": ["02:00 PM", "02:30 PM", "03:00 PM", "03:30 PM"],
}

SYMPTOM_CONDITIONS = {
    "chest pain": {
        "condition": "Possible cardiac event",
        "severity": "high",
        "keywords": ["chest pain", "chest"],
    },
    "shortness of breath": {
        "condition": "Respiratory distress",
        "severity": "high",
        "keywords": ["shortness of breath", "breathing", "breath"],
    },
    "dizziness": {
        "condition": "Circulatory issue",
        "severity": "medium",
        "keywords": ["dizziness", "dizzy", "lightheaded"],
    },
    "headache": {
        "condition": "Tension headache",
        "severity": "low",
        "keywords": ["headache", "head pain"],
    },
    "runny nose": {
        "condition": "Upper respiratory infection",
        "severity": "low",
        "keywords": ["runny nose", "congestion", "nasal"],
    },
    "swollen ankle": {
        "condition": "Possible sprain",
        "severity": "medium",
        "keywords": ["swollen", "ankle", "twisted", "sprain"],
    },
}

_tool_results = {}


def clean_response(text: str) -> str:
    return re.sub(r"<thinking>.*?</thinking>", "", str(text), flags=re.DOTALL).strip()


def run_agent_with_retry(agent_builder, prompt: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            agent = agent_builder()
            result = agent(prompt)
            return clean_response(result)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2**attempt
                print(f"[Retry ({attempt + 1})/{max_retries}] ({e.__class__.__name__}), waiting ({wait}s...)")
                time.sleep(wait)
            else:
                print(f"[Failed] ({e.__class__.__name__}) after ({max_retries}) attempts")
                raise


def build_symptom_analyzer() -> Agent:
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=AWS_REGION,
        temperature=0.0,
    )

    @tool
    def lookup_symptoms(complaint_text: str) -> str:
        """Parse a patient complaint and match symptoms against the knowledge base.

        Args:
            complaint_text: The raw patient complaint text

        Returns:
            JSON string with matched symptoms, conditions, and severity levels
        """
        complaint_lower = complaint_text.lower()
        matches = []
        for symptom, info in SYMPTOM_CONDITIONS.items():
            for kw in info["keywords"]:
                if kw in complaint_lower:
                    matches.append(
                        {
                            "symptom": symptom,
                            "condition": info["condition"],
                            "severity": info["severity"],
                        }
                    )
                    break
        result = json.dumps(
            {"matched_symptoms": matches, "total_matches": len(matches)}, indent=2
        )
        _tool_results["symptoms"] = result
        return result

    system_prompt = """You are a Symptom Analyzer agent. Your ONLY job is symptom analysis.
Call the lookup_symptoms tool with the patient's complaint text.
After the tool returns, output ONLY the raw JSON result. Do not classify urgency or book appointments."""

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[lookup_symptoms],
    )


def build_urgency_classifier() -> Agent:
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=AWS_REGION,
        temperature=0.0,
    )

    @tool
    def classify_urgency(symptom_json: str) -> str:
        """Classify triage urgency based on symptom analysis results.

        Rules:
        - If ANY severity is "high" -> urgency = "urgent"
        - If ANY severity is "medium" (none high) -> urgency = "standard"
        - If all severities are "low" -> urgency = "routine"

        Args:
            symptom_json: JSON string from the Symptom Analyzer

        Returns:
            JSON string with urgency level and reasoning
        """
        severities = []
        try:
            data = json.loads(symptom_json)
            symptoms = data.get("matched_symptoms", [])
            severities = [s.get("severity", "low") for s in symptoms]
        except (json.JSONDecodeError, AttributeError, TypeError):
            text_lower = symptom_json.lower()
            if "high" in text_lower:
                severities.append("high")
            if "medium" in text_lower:
                severities.append("medium")
            if "low" in text_lower:
                severities.append("low")
        if not severities:
            severities.append("low")

        if "high" in severities:
            urgency = "urgent"
            reason = "High-severity symptoms detected - possible cardiac or respiratory event"
        elif "medium" in severities:
            urgency = "standard"
            reason = "Medium-severity symptoms - requires same-day attention"
        else:
            urgency = "routine"
            reason = "Low-severity symptoms - suitable for routine appointment"

        result = json.dumps(
            {"urgency": urgency, "reason": reason, "severity_breakdown": severities},
            indent=2,
        )
        _tool_results["urgency"] = result
        return result

    system_prompt = """You are an Urgency Classifier agent. Your ONLY job is urgency classification.
You will receive symptom analysis JSON. Call the classify_urgency tool with that JSON.
After the tool returns, output ONLY the raw JSON result. Do not analyze symptoms or book appointments."""

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[classify_urgency],
    )


def build_appointment_scheduler() -> Agent:
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=AWS_REGION,
        temperature=0.0,
    )

    @tool
    def book_appointment(patient_id: str, urgency_level: str) -> str:
        """Book an appointment slot based on urgency level.

        Args:
            patient_id: The patient's unique identifier
            urgency_level: One of "urgent", "standard", or "routine"

        Returns:
            JSON string with booking confirmation and assigned time slot
        """
        urgency_key = urgency_level.lower().strip()
        slots = AVAILABLE_SLOTS.get(urgency_key, AVAILABLE_SLOTS["routine"])
        if not slots:
            return json.dumps(
                {
                    "status": "no_availability",
                    "message": f"No {urgency_key} slots available.",
                }
            )
        assigned_slot = slots[0]
        today = datetime.now().strftime("%Y-%m-%d")
        result = json.dumps(
            {
                "status": "booked",
                "patient_id": patient_id,
                "date": today,
                "time_slot": assigned_slot,
                "urgency": urgency_key,
                "instructions": {
                    "urgent": "Proceed to emergency intake immediately.",
                    "standard": "Please arrive 15 minutes early for intake.",
                    "routine": "Please arrive 10 minutes before your appointment.",
                }.get(urgency_key, "Please arrive on time."),
            },
            indent=2,
        )
        _tool_results["booking"] = result
        return result

    system_prompt = """You are an Appointment Scheduler agent. Your ONLY job is booking appointments.
You will receive a patient_id and urgency_level. Call the book_appointment tool with those values.
After the tool returns, output ONLY the raw JSON result. Do not analyze symptoms or classify urgency."""

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[book_appointment],
    )


def run_triage_pipeline(patient: dict) -> dict:
    print("[1/3] Symptom Analyzer...")
    _tool_results.clear()
    run_agent_with_retry(
        build_symptom_analyzer, f"Analyze these symptoms: {patient['complaint']} {patient['symptoms']}"
    )
    symptom_json = json.loads(_tool_results.get("symptoms", '{"matched_symptoms": [], "total_matches": 0}'))
    print(f"Matched ({symptom_json.get('total_matches', 0)}) symptoms")

    print("[2/3] Urgency Classifier...")
    symptom_str = json.dumps(symptom_json)
    run_agent_with_retry(
        build_urgency_classifier,
        f"Classify urgency for this symptom analysis: {symptom_str}",
    )
    urgency_json = json.loads(_tool_results.get("urgency", '{"urgency": "routine"}'))
    urgency_level = urgency_json.get("urgency", "routine")
    print(f"Urgency: ({urgency_level})")

    print("[3/3] Appointment Scheduler...")
    run_agent_with_retry(
        build_appointment_scheduler,
        f"Book an appointment for patient_id={patient['patient_id']} with urgency_level={urgency_level}",
    )
    booking_json = json.loads(_tool_results.get("booking", '{"status": "failed"}'))
    print(f"Slot: ({booking_json.get('time_slot', 'N/A')})")

    return {
        "patient": patient["name"],
        "symptoms": symptom_json,
        "urgency": urgency_json,
        "booking": booking_json,
    }
