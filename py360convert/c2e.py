from typing import Literal, Union, overload

import numpy as np
from numpy.typing import NDArray

from .utils import (
    CubeFaceSampler,
    CubeFormat,
    DType,
    Face,
    InterpolationMode,
    cube_dice2list,
    cube_dict2list,
    cube_h2list,
    equirect_facetype,
    equirect_uvgrid,
    mode_to_order,
)


@overload
def c2e(
    cubemap: NDArray[DType],
    h: int,
    w: int,
    mode: InterpolationMode = "bilinear",
    cube_format: Literal["horizon", "dice"] = "dice",
) -> NDArray[DType]: ...


@overload
def c2e(
    cubemap: list[NDArray[DType]],
    h: int,
    w: int,
    mode: InterpolationMode = "bilinear",
    cube_format: Literal["list"] = "list",
) -> NDArray[DType]: ...


@overload
def c2e(
    cubemap: dict[str, NDArray[DType]],
    h: int,
    w: int,
    mode: InterpolationMode = "bilinear",
    cube_format: Literal["dict"] = "dict",
) -> NDArray[DType]: ...


def c2e(
    cubemap: Union[NDArray[DType], list[NDArray[DType]], dict[str, NDArray[DType]]],
    h: int,
    w: int,
    mode: InterpolationMode = "bilinear",
    cube_format: CubeFormat = "dice",
) -> NDArray:
    """Convert the cubemap to equirectangular.

    Parameters
    ----------
    cubemap: Union[NDArray, list[NDArray], dict[str, NDArray]]
    h: int
        Output equirectangular height.
    w: int
        Output equirectangular width.
    mode: Literal["bilinear", "nearest"]
        Interpolation mode.
    cube_format: Literal["horizon", "list", "dict", "dice"]
        Format of input cubemap.

    Returns
    -------
    np.ndarray
        Equirectangular image.
    """
    order = mode_to_order(mode)
    if w % 8 != 0:
        raise ValueError("w must be a multiple of 8.")

    if cube_format == "horizon":
        if not isinstance(cubemap, np.ndarray):
            raise TypeError('cubemap must be a numpy array for cube_format="horizon"')
        if cubemap.ndim == 2:
            cubemap = cubemap[..., None]
            squeeze = True
        else:
            squeeze = False
        cube_faces = cube_h2list(cubemap)
    elif cube_format == "list":
        if not isinstance(cubemap, list):
            raise TypeError('cubemap must be a list for cube_format="list"')
        if len({x.shape for x in cubemap}) != 1:
            raise ValueError("All cubemap elements must have same shape")
        if cubemap[0].ndim == 2:
            cube_faces = [x[..., None] for x in cubemap]
            squeeze = True
        else:
            cube_faces = cubemap
            squeeze = False
    elif cube_format == "dict":
        if not isinstance(cubemap, dict):
            raise TypeError('cubemap must be a dict for cube_format="dict"')
        if len({x.shape for x in cubemap.values()}) != 1:
            raise ValueError("All cubemap elements must have same shape")
        if cubemap["F"].ndim == 2:
            cubemap = {k: v[..., None] for k, v in cubemap.items()}
            squeeze = True
        else:
            squeeze = False
        cube_faces = cube_dict2list(cubemap)
    elif cube_format == "dice":
        if not isinstance(cubemap, np.ndarray):
            raise TypeError('cubemap must be a numpy array for cube_format="dice"')
        if cubemap.ndim == 2:
            cubemap = cubemap[..., None]
            squeeze = True
        else:
            squeeze = False
        cube_faces = cube_dice2list(cubemap)
    else:
        raise ValueError('Unknown cube_format "{cube_format}".')

    cube_faces = np.stack(cube_faces)

    if cube_faces.shape[1] != cube_faces.shape[2]:
        raise ValueError("Cubemap faces must be square.")
    face_w = cube_faces.shape[2]

    u, v = equirect_uvgrid(h, w)

    # Get face id to each pixel: 0F 1R 2B 3L 4U 5D
    tp = equirect_facetype(h, w)

    coor_x = np.empty((h, w), dtype=np.float32)
    coor_y = np.empty((h, w), dtype=np.float32)
    face_w2 = face_w / 2

    # Middle band (front/right/back/left)
    mask = tp < Face.UP
    angles = u[mask] - (np.pi / 2 * tp[mask])
    tan_angles = np.tan(angles)
    cos_angles = np.cos(angles)
    tan_v = np.tan(v[mask])

    coor_x[mask] = face_w2 * tan_angles
    coor_y[mask] = -face_w2 * tan_v / cos_angles

    mask = tp == Face.UP
    c = face_w2 * np.tan(np.pi / 2 - v[mask])
    coor_x[mask] = c * np.sin(u[mask])
    coor_y[mask] = c * np.cos(u[mask])

    mask = tp == Face.DOWN
    c = face_w2 * np.tan(np.pi / 2 - np.abs(v[mask]))
    coor_x[mask] = c * np.sin(u[mask])
    coor_y[mask] = -c * np.cos(u[mask])

    # Final renormalize
    coor_x += face_w2
    coor_y += face_w2
    coor_x.clip(0, face_w, out=coor_x)
    coor_y.clip(0, face_w, out=coor_y)

    equirec = np.empty((h, w, cube_faces.shape[3]), dtype=cube_faces[0].dtype)
    sampler = CubeFaceSampler(tp, coor_x, coor_y, order, face_w, face_w)
    for i in range(cube_faces.shape[3]):
        equirec[..., i] = sampler(cube_faces[..., i])

    return equirec[..., 0] if squeeze else equirec
