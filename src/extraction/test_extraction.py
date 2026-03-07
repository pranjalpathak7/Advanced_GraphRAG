import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

# --- Configuration for GitHub Models ---
# We use the GITHUB_TOKEN as the API Key
api_key = os.getenv("GITHUB_TOKEN")
if not api_key:
    raise ValueError("❌ GITHUB_TOKEN is missing in .env file!")

# We point to the Azure/GitHub inference endpoint
# This lets us use GPT-4o for FREE
llm = ChatOpenAI(
    model="gpt-4o",
    openai_api_key=api_key,
    openai_api_base="https://models.inference.ai.azure.com",
    temperature=0
)

# --- Define a Simple Test Schema ---
class TestExtraction(BaseModel):
    person_name: str = Field(description="Name of the person mentioned")
    tool_name: str = Field(description="Name of the tool mentioned")
    action: str = Field(description="What the person did with the tool")

# --- Run the Test ---
def run_test():
    print("🚀 Connecting to GitHub Models (GPT-4o)...")
    
    try:
        # We use 'with_structured_output' to force JSON adherence
        structured_llm = llm.with_structured_output(TestExtraction)
        
        text = "Yesterday, Alice fixed a critical bug in the Redis database."
        print(f"📥 Input Text: '{text}'")
        
        result = structured_llm.invoke(text)
        
        print("\n✅ Extraction Successful!")
        print(f"   Name:   {result.person_name}")
        print(f"   Tool:   {result.tool_name}")
        print(f"   Action: {result.action}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Tip: Ensure your GITHUB_TOKEN is correct in .env")

if __name__ == "__main__":
    run_test()