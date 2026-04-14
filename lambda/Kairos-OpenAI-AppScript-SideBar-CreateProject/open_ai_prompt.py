import json, logging
from openai import OpenAI

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def generate_openai_result(
    user_prompt: str,
    client: OpenAI,
    config_client,
    max_retries: int = 3
):
    """
    Responses API version of your function-calling flow.

    - Forces a tool call (like function_call={"name": ...})
    - Extracts tool call arguments from response.output
    - Returns (parsed_json, response)
    """
    createConfig = config_client.get_config()

    llm = createConfig.get("llm_settings", {})
    model = llm.get("model", "gpt-4.1")
    temperature = llm.get("temperature", 0.3)
    max_tokens = llm.get("token", 3000)

    prompt = createConfig.get("prompt_content", {})
    system_content = prompt.get("system_content", "")

    project_schema = createConfig.get("project_schema", {})
    functions_config = createConfig.get("functions", {})
    functions_name = functions_config.get("name")
    functions_description = functions_config.get("description")

    # Responses API uses `tools` not `functions`
    tools = [
        {
            "type": "function",
            "name": functions_name,
            "description": functions_description,
            "parameters": project_schema,
        }
    ]

    # Responses API uses `instructions` + `input`
    response = client.responses.create(
        model=model,
        instructions=system_content,
        input=f"Request:\n{json.dumps(user_prompt)}",
        tools=tools,
        tool_choice={"type": "function", "name": functions_name},  # force tool call
        temperature=temperature,
        max_output_tokens=max_tokens,
    )

    # --- Extract the tool call safely (objects, not dicts) ---
    tool_call = None
    for item in getattr(response, "output", []) or []:
        # item is usually a typed object in Responses API
        if getattr(item, "type", None) == "function_call" and getattr(item, "name", None) == functions_name:
            tool_call = item
            break

    if not tool_call or not getattr(tool_call, "arguments", None):
        raise RuntimeError("No function call arguments returned by Responses API")

    args_str = tool_call.arguments


    try:
        return json.loads(args_str), response
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse function call arguments: {e}\nArguments:\n{args_str}")