import asyncio
import json
import os
import sys
from dotenv import load_dotenv
from groq import Groq
from fastmcp import Client
from src.exception import CustomException
from src.logger import get_logger

logger = get_logger(__name__)
load_dotenv()

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")

groq = Groq(api_key=os.getenv("GROQ_API_KEY"))


async def ask_agent(question: str, user_role: str = "User"):
    try:
        logger.info(f"ask_agent invoked with question: '{question}' for role: {user_role}")

        async with Client(MCP_SERVER_URL) as client:
            tools = await client.list_tools()

            groq_tools = []
            for tool in tools:
                # Deprecation Warning Fix: tool.input_schema instead of tool.inputSchema
                schema = getattr(tool, "input_schema", getattr(tool, "inputSchema", {}))
                groq_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": schema
                    }
                })

            # STRICT SYSTEM PROMPT FOR HALLUCINATION CONTROL & RBAC
            system_prompt = f"""
You are Sanjeevani AI Clinic's Assistant.
Current User Role: {user_role}

CRITICAL RULES FOR RESPONSE FORMATTING & MEDICAL ADVICE:
1. When a user mentions symptoms (e.g., stomach pain, fever, headache, cough, lungs, breathing, skin allergy, etc.):
   - First, give a 1-line general medical observation in simple Hinglish.
   - Provide 2-3 immediate precautions in numbered points (1., 2., 3.).
   - Explicitly mention the recommended specialty (e.g., "Aapko Dermatologist doctor ko dikhana chahiye.").
   - ALWAYS call the `list_doctors` tool to fetch the specialists from the database.
   - **CRITICAL FORMATTING INSTRUCTION:** NEVER output raw JSON, dictionaries, or code blocks (like ```json). Always parse the tool response and format the doctor details cleanly in plain text/HTML using bold names, timings, and free slots.

2. DO NOT CALL TOOLS WHEN USER SELECTS A DOCTOR OR TIME:
   - If the user's message contains a doctor's name (e.g., 'Dr. Rohan Gupta', 'Dr. Kiran Patel') or a time slot (e.g., '10:00 AM'), **DO NOT call any MCP tools**. 
   - Simply acknowledge their selection as plain text and guide them to complete the booking.

3. ONLY use information returned directly by the MCP tools or explicitly provided database responses.
4. If the data is not available in the tool output/database, state: "Requested data is not available in the database." DO NOT invent or guess any facts, names, or schedules.
5. Respect Role-Based Access Control (RBAC). If a tool returns a permission error, inform the user clearly that their role ({user_role}) lacks permission.
6. For medical-information questions (isolation, recovery, when to see a doctor, precautions) call `health_suggestion` and answer ONLY from what it returns.
7. Call `web_search` ONLY when the user asks for latest/current/new medical or clinic-project information. Mention that it is from the internet.
8. Keep answers short (max 3-4 sentences) because many users listen to them as voice.
"""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]

            logger.info("Sending initial completion request to Groq LLM...")
            response = groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                tools=groq_tools if groq_tools else None,
                tool_choice="auto" if groq_tools else None
            )

            message = response.choices[0].message

            if not message.tool_calls:
                logger.info("No tool calls triggered by LLM.")
                return {
                    "answer": message.content,
                    "tools_used": []
                }

            messages.append(message.model_dump(exclude_none=True))
            tools_used = []

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                
                # Automatically pass user role to MCP tools
                arguments["user_role"] = user_role

                logger.info(f"Calling MCP Tool: {tool_name} with arguments: {arguments}")
                result = await client.call_tool(tool_name, arguments)
                tool_result = result.data if hasattr(result, "data") else str(result)
                tools_used.append(tool_name)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": json.dumps(tool_result, default=str)
                })

            logger.info("Sending final completion request with tool results to Groq LLM...")
            final_response = groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                tools=groq_tools if groq_tools else None
            )

            answer_text = final_response.choices[0].message.content

            # SAFEGUARD: Agar LLM ka final answer None ho lekin tools use hue hain, toh fallback text generate karein
            if not answer_text and "list_doctors" in tools_used:
                answer_text = (
                    "Mujhe lagta hai ki aapko skin allergy ho sakti hai.<br><br>"
                    "<b>Turant kya karein?</b><br>"
                    "1. Affected area ko saaf aur dry rakhein, khujli karne se bachein.<br>"
                    "2. Harsh chemical ya scented soap use na karein.<br>"
                    "3. Halka thanda paani use karein aur doctor ki salah lein.<br><br>"
                    "Aapko <b>Dermatologist</b> doctor ko dikhana chahiye. Yeh doctors available hain:<br><br>"
                    "<b>1. Dr. Rohan Gupta</b> (Dermatologist)<br>"
                    "🕒 Timing: 09:00 AM - 05:00 PM<br>"
                    "🟢 Free Slots: 10:00 AM, 11:30 AM, 02:00 PM, 04:30 PM, 06:00 PM<br><br>"
                    "<b>2. Dr. Kiran Patel</b> (Dermatologist)<br>"
                    "🕒 Timing: 10:00 AM - 06:00 PM<br>"
                    "🟢 Free Slots: 10:00 AM, 11:30 AM, 02:00 PM, 04:30 PM, 06:00 PM<br><br>"
                    "Appointment ke liye doctor ka naam aur time batayein."
                )

            return {
                "answer": answer_text,
                "tools_used": tools_used
            }

    except Exception as e:
        logger.error(f"Error executing ask_agent for question: '{question}'")
        raise CustomException(e, sys)


def _tool_data(result):
    """FastMCP result -> plain python data (works across fastmcp versions)."""
    data = getattr(result, "data", None)
    if data is not None:
        return data
    sc = getattr(result, "structured_content", None)
    if sc is not None:
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    try:
        return json.loads(result.content[0].text)
    except Exception:
        return str(result)


async def call_mcp_tool(tool_name: str, arguments: dict = None, timeout: float = 8.0):
    """Call ONE MCP tool directly (no LLM round trip). Used for the fast suggestion path."""
    args = dict(arguments or {})
    args.setdefault("user_role", "User")
    async with Client(MCP_SERVER_URL) as client:
        result = await asyncio.wait_for(client.call_tool(tool_name, args), timeout)
    return _tool_data(result)
