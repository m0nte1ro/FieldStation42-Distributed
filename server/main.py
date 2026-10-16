import logging

from server.api.app import run

# the server: web console, catalog and schedule API, the client API, and the schedule keeper
logging.basicConfig(format="%(asctime)s %(levelname)s:%(name)s:%(message)s", level=logging.INFO)

if __name__ == "__main__":
    run()
