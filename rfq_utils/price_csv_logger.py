import csv
import os
import queue
import threading
import time


class PriceLogger:
    """Logs prices to CSV file using a background thread for non-blocking writes."""

    FIELDNAMES = ("timestamp", "ticker", "price")

    def __init__(
        self,
        csv_path: str = "prices.csv",
        batch_size: int = 200,
        flush_interval: float = 0.5,
        alert_queue_threshold: int = 1000,
        alert_delay_threshold: float = 5.0,
    ):
        self.csv_path = csv_path
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.alert_queue_threshold = alert_queue_threshold
        self.alert_delay_threshold = alert_delay_threshold
        self._queue: "queue.Queue[tuple]" = queue.Queue(maxsize=10_000)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._last_alert_time = 0.0

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        if self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=5)

    def log(self, timestamp: int, ticker: str, price: float) -> None:
        try:
            self._queue.put_nowait((timestamp, ticker, price))
            self._check_queue_health()
        except queue.Full:
            now = time.time()
            if now - self._last_alert_time > 10.0:
                print(f"⚠️  CSV queue full: dropping event")
                self._last_alert_time = now

    def _check_queue_health(self) -> None:
        queue_size = self._queue.qsize()
        if queue_size > self.alert_queue_threshold:
            now = time.time()
            if now - self._last_alert_time > 10.0:
                print(f"⚠️  CSV queue overloaded: {queue_size} events pending")
                self._last_alert_time = now

    def _run(self) -> None:
        file_exists = os.path.exists(self.csv_path) and os.path.getsize(self.csv_path) > 0
        f = open(self.csv_path, mode="a", newline="", buffering=1024 * 1024)
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(self.FIELDNAMES)
            f.flush()

        batch: list[tuple] = []
        last_flush = time.monotonic()

        try:
            while not self._stop_event.is_set() or not self._queue.empty():
                timeout = max(0.0, self.flush_interval - (time.monotonic() - last_flush))
                try:
                    item = self._queue.get(timeout=timeout)
                    batch.append(item)
                except queue.Empty:
                    pass

                time_since_flush = time.monotonic() - last_flush
                if time_since_flush > self.alert_delay_threshold and batch:
                    now = time.time()
                    if now - self._last_alert_time > 10.0:
                        print(f"⚠️  CSV flush delayed: {time_since_flush:.1f}s, {len(batch)} events pending")
                        self._last_alert_time = now

                should_flush = batch and (
                    len(batch) >= self.batch_size
                    or time.monotonic() - last_flush >= self.flush_interval
                )
                if should_flush:
                    writer.writerows(batch)
                    f.flush()
                    batch = []
                    last_flush = time.monotonic()

            if batch:
                writer.writerows(batch)
                f.flush()
        finally:
            f.close()
