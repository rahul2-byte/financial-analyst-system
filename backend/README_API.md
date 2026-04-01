# Financial Intelligence Platform - API Service

## Overview
This is the backend API service built with FastAPI. It uses an on-demand `llama.cpp` server for LLM inference and streams responses via Server-Sent Events (SSE).

The path resolution is designed to be portable. The application can be run from the project's root directory (the one containing `backend`, `frontend`, etc.), and it will correctly locate the `llama.cpp` binary and model files.

## Prerequisites
1.  **Python 3.11+**
2.  **`llama.cpp` compiled:** The `llama-server` binary must be available.
3.  **A GGUF model file.**

## Setup

1.  **Install Dependencies**:
    From the `backend` directory, run:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configuration**:
    The service is configured via `backend/config/llm_config.yaml`.

    **You must edit this file before running the application.**
    
    You need to provide **absolute paths** for the `llama.cpp` binary and the model file.
    - `binary_path`: The full, absolute path to your `llama-server` executable.
    - `model_path`: The full, absolute path to your `.gguf` model file.

    Example:
    ```yaml
    llama_server:
      binary_path: "/home/user/llama.cpp/build/bin/llama-server"
      model_path: "/home/user/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
    ```

3. **Model assets and runtime setup**:
    Ensure all required local model assets are present and that `backend/config/llm_config.yaml`
    points to valid local paths. Keep runtime dependencies local/offline for deterministic behavior.

## Running the Server

The `llama.cpp` server is started **on-demand** when the first API request is made.

To run the main FastAPI application, execute the following command **from the `backend` directory**:

```bash
uvicorn app.main:app --reload --port 8000
```

The `llama.cpp` server process logs can be found in `backend/logs/llama_server.log`. Check this file if you encounter issues with the model not starting.

## API Endpoints

-   `POST /api/chat`: Chat with the LLM (Streaming). This will start the server if it's not running.
-   `GET /api/health`: Check service health. This will also trigger a server start if it's offline.
-   `GET /docs`: OpenAPI documentation.

## Architecture

-   **`backend/app/main.py`**: Entry point, handles application lifespan (server cleanup).
-   **`backend/app/config.py`**: Loads and validates configuration from `config/llm_config.yaml`. It resolves all paths to be absolute.
-   **`backend/app/core/llama_manager.py`**: Manages the on-demand lifecycle of the `llama.cpp` server process.
-   **`backend/app/services/llama_cpp_service.py`**: Implements the `LLMServiceInterface` to communicate with the `llama.cpp` server.
