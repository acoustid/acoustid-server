from typing import Any, Dict, Optional

import requests


class NSQPublisher:
    def __init__(
        self, nsqd_http_address: str, pool_connections: int = 10, pool_maxsize: int = 10
    ):
        """
        Initialize the NSQPublisher with the address of the nsqd HTTP server and connection pooling.

        :param nsqd_http_address: The HTTP address of the nsqd server (e.g., "http://localhost:4151").
        :param pool_connections: The number of connection pools to keep alive.
        :param pool_maxsize: The maximum number of connections to keep in the pool.
        """
        self.nsqd_http_address = nsqd_http_address

        # Create a session with connection pooling
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=pool_connections, pool_maxsize=pool_maxsize
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def publish(self, topic: str, message: bytes) -> bool:
        """
        Publish a message to a specified NSQ topic.

        :param topic: The NSQ topic to publish the message to.
        :param message: The message to publish.
        :return: True if the message was published successfully, False otherwise.
        """
        url = f"{self.nsqd_http_address}/pub?topic={topic}"
        try:
            response = self.session.post(url, data=message)
            if response.status_code == 200:
                return True
            else:
                print(
                    f"Failed to publish message: {response.status_code} - {response.text}"
                )
                return False
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return False

    def publish_json(self, topic: str, payload: Dict[str, Any]) -> bool:
        """
        Publish a JSON payload to a specified NSQ topic.

        :param topic: The NSQ topic to publish the message to.
        :param payload: The JSON payload to publish.
        :return: True if the message was published successfully, False otherwise.
        """
        import json

        message = json.dumps(payload).encode("utf8")
        return self.publish(topic, message)

    def close(self):
        """
        Close the session and release connection pool resources.
        """
        self.session.close()


# Example usage
if __name__ == "__main__":
    # Initialize the publisher with the nsqd HTTP address and connection pooling
    publisher = NSQPublisher(
        "http://localhost:4151", pool_connections=5, pool_maxsize=5
    )

    try:
        # Publish a simple message
        topic = "test_topic"
        message = b"Hello, NSQ!"
        if publisher.publish(topic, message):
            print("Message published successfully!")
        else:
            print("Failed to publish message.")

        # Publish a JSON payload
        payload = {
            "event": "user_signup",
            "user_id": 12345,
            "email": "user@example.com",
        }
        if publisher.publish_json(topic, payload):
            print("JSON payload published successfully!")
        else:
            print("Failed to publish JSON payload.")
    finally:
        # Ensure the session is closed to release resources
        publisher.close()
