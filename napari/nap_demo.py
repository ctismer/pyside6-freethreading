import sys
import numpy as np
import napari

print("GIL enabled:", sys._is_gil_enabled(), flush=True)

rng = np.random.default_rng(0)
stack = rng.random((32, 512, 512)).astype("float32")

viewer = napari.Viewer(title="napari on free-threaded PySide6")
viewer.add_image(stack, name="random stack", colormap="viridis")

import qtpy
print("binding:", qtpy.API_NAME, flush=True)
print("GIL with window open:", sys._is_gil_enabled(), flush=True)

napari.run()
