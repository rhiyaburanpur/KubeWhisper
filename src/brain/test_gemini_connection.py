"""
Diagnostic script to verify Google GenAI SDK setup and available models.
"""
import os
from google import genai
from dotenv import load_dotenv

def test_connection():
    print("GOOGLE GENAI SDK DIAGNOSTIC\n")
    
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in .env file")
        return False
    
    print(f"API Key found: {api_key[:8]}...{api_key[-4:]}\n")
    
    try:
        client = genai.Client(api_key=api_key)
        print("Client initialized successfully\n")
    except Exception as e:
        print(f"Client initialization failed: {e}")
        return False
    
    print("Available Gemini Models:")
    print("-" * 50)
    try:
        models = client.models.list(config={"page_size": 20})
        
        flash_models = []
        pro_models = []
        
        for m in models:
            model_name = m.name
            print(f"  {model_name}")
            
            if 'flash' in model_name.lower():
                flash_models.append(model_name)
            elif 'pro' in model_name.lower():
                pro_models.append(model_name)
        
        print("\n" + "=" * 50)
        print("RECOMMENDED FOR KUBEWHISPERER:")
        print("=" * 50)
        
        if flash_models:
            print(f"\nFast & Cost-Effective: {flash_models[0]}")
            print(f"   (Use this for production)")
        
        if pro_models:
            print(f"\nMost Capable: {pro_models[0]}")
            print(f"   (Use for complex reasoning)")
            
    except Exception as e:
        print(f"Failed to list models: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("TESTING API CALL")
    print("=" * 50)
    
    try:
        test_model = flash_models[0] if flash_models else "models/gemini-1.5-flash"
        print(f"\nUsing model: {test_model}")
        
        response = client.models.generate_content(
            model=test_model,
            contents="Say 'KubeWhisperer is online!' in exactly 5 words."
        )
        
        print(f"\nResponse received:")
        print(f"  {response.text}\n")
        
        print("=" * 50)
        print("ALL TESTS PASSED - GEMINI SDK READY")
        print("=" * 50)
        return True
        
    except Exception as e:
        print(f"\nAPI call failed: {e}")
        print(f"\nError type: {type(e).__name__}")
        print(f"Error details: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_connection()
    exit(0 if success else 1)