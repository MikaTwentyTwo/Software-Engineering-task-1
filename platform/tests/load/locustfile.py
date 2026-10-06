import os
import uuid
from datetime import datetime, timedelta, timezone

import gevent
from locust import HttpUser, between, task
from locust.exception import StopUser


class CampusUser(HttpUser):
    wait_time = between(2, 4)

    def on_start(self):
        self.client.trust_env = False
        self.booking_id = None

        admin_token = self.login("admin", "ADMIN_PASSWORD")
        student_token = self.login("student", "STUDENT_PASSWORD")
        self.headers = {"Authorization": f"Bearer {student_token}"}

        with self.client.post(
            "/api/rooms/resources",
            json={
                "name": "Locust-" + uuid.uuid4().hex[:12],
                "capacity": 10,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
            name="setup: create room",
            catch_response=True,
            timeout=10,
        ) as response:
            if response.status_code != 201:
                response.failure(f"Room creation: HTTP {response.status_code}")
                raise StopUser()
            self.resource_id = response.json()["id"]

        # Wait for the resource projection in the bookings service.
        for _ in range(30):
            with self.client.get(
                "/api/bookings/resources",
                headers=self.headers,
                name="setup: resource projection",
                catch_response=True,
                timeout=10,
            ) as response:
                if response.status_code == 200:
                    if any(
                        item["id"] == self.resource_id
                        for item in response.json()
                    ):
                        return
                else:
                    response.failure(
                        f"Projection read: HTTP {response.status_code}"
                    )
            gevent.sleep(1)

        raise StopUser()

    def login(self, username, password_variable):
        with self.client.post(
            "/api/users/login",
            json={
                "username": username,
                "password": os.environ[password_variable],
            },
            name=f"setup: login {username}",
            catch_response=True,
            timeout=10,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Login: HTTP {response.status_code}")
                raise StopUser()
            return response.json()["access_token"]

    def cancel_booking(self):
        with self.client.delete(
            f"/api/bookings/bookings/{self.booking_id}",
            headers=self.headers,
            name="cancel booking",
            catch_response=True,
            timeout=10,
        ) as response:
            if response.status_code == 200:
                self.booking_id = None
            else:
                response.failure(
                    f"Cancellation: HTTP {response.status_code}"
                )

    @task(3)
    def booking_cycle(self):
        # Retry cancellation before creating another reservation.
        if self.booking_id is not None:
            self.cancel_booking()
            return

        start = datetime.now(timezone.utc) + timedelta(days=1)
        headers = {
            **self.headers,
            "Idempotency-Key": uuid.uuid4().hex,
        }

        with self.client.post(
            "/api/bookings/bookings",
            json={
                "resource_id": self.resource_id,
                "start": start.isoformat(),
                "end": (start + timedelta(minutes=30)).isoformat(),
            },
            headers=headers,
            name="create booking",
            catch_response=True,
            timeout=10,
        ) as response:
            if response.status_code != 201:
                response.failure(
                    f"Booking creation: HTTP {response.status_code}"
                )
                return
            self.booking_id = response.json()["id"]

        self.cancel_booking()

    @task(1)
    def read_resources(self):
        self.client.get(
            "/api/bookings/resources",
            headers=self.headers,
            name="list resources",
            timeout=10,
        )

    def on_stop(self):
        if self.booking_id is not None:
            self.cancel_booking()