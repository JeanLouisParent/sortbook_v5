# Project Overview

This project provides the configuration to deploy and run n8n, a workflow automation tool, using Docker. It is designed to work with an existing Traefik reverse proxy setup (presumably from a `docker-toolkit` project) to expose the n8n service securely.

The setup consists of:
- A `docker-compose.yml` file that defines the n8n service.
- An `n8n/.env` file that contains the environment variables for configuring n8n, such as hostname, protocol, and encryption key.
- Data persistence is handled by a Docker volume named `n8n_data`.

# Building and Running

To run this project, you need to have Docker and Docker Compose installed. The project relies on an external network created by a `docker-toolkit`, which should be running before you start this project.

1.  **Start the Traefik reverse proxy:**
    It is assumed that you have a `docker-toolkit` project located at `~/docker-toolkit`.
    ```bash
    cd ~/docker-toolkit
    docker compose up -d
    ```

2.  **Start the n8n service:**
    From this project's root directory (`/home/antares/project/sortbook_v5`), run the following command:
    ```bash
    docker compose up -d
    ```

After these steps, n8n should be accessible at `https://n8n.antares.local/`. You might need to add `n8n.antares.local` to your `/etc/hosts` file, pointing to your local machine.

# Development Conventions

- The n8n service is defined in `docker-compose.yml`.
- All n8n-specific configurations are stored in `n8n/.env`.
- The n8n container is named `n8n`.
- The application is connected to an external Docker network named `docker-toolkit_default` for proxying through Traefik.
