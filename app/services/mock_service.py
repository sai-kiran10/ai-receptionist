from llm_interface import LLMInterface
class MockService(LLMInterface):
    def generate_response(self, prompt: str) -> str:
        return "I am a fake AI for testing. I don't use any API credits!"