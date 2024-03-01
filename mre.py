from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from multiprocessing import Manager
from queue import Empty as QueueEmptyException
from typing import Optional
import depthai
import trio

class Camera:
    def __init__(
        self,
    ) -> None:
        
        self._pipeline = depthai.Pipeline()

        self._camera = self._pipeline.create(depthai.node.ColorCamera)
        self._camera.setResolution(depthai.ColorCameraProperties.SensorResolution.THE_4_K)

        self._manip = self._pipeline.create(depthai.node.ImageManip)
        self._manip.setMaxOutputFrameSize(
            int(
                self._camera.getResolutionHeight()
                * (0.5740000009536743 - 0.11999999731779099)
                * self._camera.getResolutionWidth()
                * (0.20800000429153442 - 0.10199999809265137)
                * 3
                * 1.01
            )
        )
        self._manip.initialConfig.setFrameType(depthai.RawImgFrame.Type.BGR888p)
        self._manip.initialConfig.setKeepAspectRatio(False)
        self._manip.initialConfig.setCropRect((0.10199999809265137, 0.11999999731779099, 0.20800000429153442, 0.5740000009536743))
        self._camera.video.link(self._manip.inputImage)

        x_video_out = self._pipeline.create(depthai.node.XLinkOut)
        x_video_out.setStreamName("video")
        x_video_out.input.setBlocking(False)
        self._manip.out.link(x_video_out.input)

        self._device: Optional[depthai.Device] = None
        self._nursery = None  

    async def connect(self) -> None:
        self._device = depthai.Device(self._pipeline, depthai.UsbSpeed.SUPER)
        self.output_queue = self._device.getOutputQueue(name="video", maxSize=1, blocking=False)

    @asynccontextmanager
    async def film(self) -> AsyncGenerator[None, None, None]:
        with Manager() as queue_manager:
            try:
                async with trio.open_nursery() as self._nursery:
                    self._queue = queue_manager.Queue(1)
                    await self._nursery.start(self._result_receiver)
                    try:
                        yield
                    finally:
                        print("cancelling...")
                        self._nursery.cancel_scope.cancel()
            finally:
                print("exiting manager")

    async def _result_receiver(
        self, task_status: trio.TaskStatus = trio.TASK_STATUS_IGNORED
    ) -> None:
        task_status.started()
        while True:
            try:
                self._queue.get_nowait()
            except QueueEmptyException:
                pass
            await trio.sleep(0)

    def close(self) -> None:
        if self._nursery is not None:
            self._nursery.cancel_scope.cancel()
        if self._device is not None:
            self._device.close()

async def main() -> None:

    while True:
        camera = Camera()
        await camera.connect()
        print("connected")

        async with camera.film():
            with trio.move_on_after(0.5):
                await trio.sleep_forever()

        camera.close()

        print("done")

if __name__ == "__main__":
    trio.run(main)