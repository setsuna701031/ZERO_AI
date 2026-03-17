import json
import requests


API_URL = "http://127.0.0.1:5000/agent/run"


def send_to_zero(user_input: str) -> dict:
    payload = {
        "input": user_input
    }

    try:
        response = requests.post(
            API_URL,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {
            "success": False,
            "mode": "client_error",
            "input": user_input,
            "plan": [],
            "results": [],
            "observations": [],
            "final_answer": f"Request failed: {exc}"
        }


def print_result(result: dict):
    print("\n[ZERO RESULT]")
    print(f"success      : {result.get('success')}")
    print(f"mode         : {result.get('mode')}")
    print(f"input        : {result.get('input')}")
    print("final_answer :")
    print(result.get("final_answer", ""))

    plan = result.get("plan", [])
    if plan:
        print("\nplan:")
        print(json.dumps(plan, ensure_ascii=False, indent=2))

    results = result.get("results", [])
    if results:
        print("\nresults:")
        print(json.dumps(results, ensure_ascii=False, indent=2))

    observations = result.get("observations", [])
    if observations:
        print("\nobservations:")
        print(json.dumps(observations, ensure_ascii=False, indent=2))

    print("-" * 60)


def main():
    print("ZERO CLI started")
    print("Type exit to quit")
    print("-" * 60)

    while True:
        try:
            user_input = input("you> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nZERO CLI stopped")
            break

        if user_input.lower() in ["exit", "quit"]:
            print("ZERO CLI stopped")
            break

        if not user_input:
            continue

        result = send_to_zero(user_input)
        print_result(result)


if __name__ == "__main__":
    main()