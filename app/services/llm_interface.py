from abc import ABC, abstractmethod

class LLMInterface(ABC):
    """
    Abstract Base Class for LLM providers.
    Ensures that any LLM service used in this project implements 
    the 'generate_response' method.
    """
    
    @abstractmethod
    def generate_response(self, prompt: str) -> str:
        """
        Takes a user string and returns a text response from the LLM.
        """
        pass