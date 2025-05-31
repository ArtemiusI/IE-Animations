#!/usr/bin/env python

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 3
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####


# Plt File documentation
#
# First 8 bytes: "PLT V1  "
# 50 4C 54 20 56 31 20 20
# Next 8 bytes: Random? But these 8 bytes always work
# 0A 00 00 00 00 00 00 00
# Next 4 bytes: width
# 00 00 00 00
# Next 4 bytes: height
# 00 00 00 00
# The rest is data:
# AA 00 BB 01 ..., with AA 00 = (value, layer), BB 01 = (value, layer)

#import gi
from gimpfu import *

import os
import struct

from array import array

# New layers can easily be added by extending this list, the script
# will automatically include them
# Add them to the end, list-position = plt-layer-idx (skin = 0)
PLT_LAYERS = ["skin", "hair", "metal1", "metal2", "cloth1", "cloth2",
              "leather1", "leather2", "tattoo1", "tattoo2"]
# Alpha value at which to consider a pixel of layer to be set, range [0,255]
LAYER_ALPHA_CUTOFF = 25


def plt_load(filename, raw_filename):
    f = open(filename, 'rb')
    # First 24 bytes contain header
    header = struct.unpack('<16s2I', f.read(24))
    if header[0][0:7] == 'PLT V1  ':
        gimp.pdb.gimp_message('Not a valid plt file' + header[0][0:8])
        f.close()
        return 1
    (width, height) = header[1], header[2]
    # Now read (color, layer) tuples - 1 byte for each value
    num_px = width * height
    plt_px = [struct.unpack('<2B', f.read(2)) for i in xrange(num_px)]
    f.close()
    # Adjust coordinates
    plt_px = [px for i in range(height)
              for px in
              plt_px[(height*width)-((i+1)*width):(height*width)-(i*width)]]

    # Create a new image
    img = gimp.Image(width, height, GRAY)
    img.filename = os.path.split(filename)[1]
    img.disable_undo()

    # Create Layers
    num_layers = len(PLT_LAYERS)
    gimp.progress_init("Creating layers ...")
    gimp.progress_update(0.0)
    for plt_id, lname in enumerate(PLT_LAYERS):
        # Create layer
        lay = gimp.Layer(img, lname, width, height,
                         GRAYA_IMAGE, 100, NORMAL_MODE)
        img.insert_layer(layer=lay, position=0)
        # Get region and write data
        region = lay.get_pixel_rgn(0, 0, width, height, True, True)
        lay_px = [[px[0], 255] if px[1] == plt_id else [0, 0] for px in plt_px]
        # Need to use tostring() to convert (in python2)
        lay_px_data = array('B', [i for sl in lay_px for i in sl]).tostring()
        region[0:width, 0:height] = lay_px_data
        # Update image and progress
        lay.flush()
        lay.merge_shadow(TRUE)
        lay.update(0, 0, width, height)
        gimp.progress_update(float(plt_id+1)/float(num_layers))

    gimp.progress_update(1.0)
    img.enable_undo()
    return img


def plt_save(img, drawable, filename, raw_filename):
    f = open(filename, 'wb')
    # Get img data
    width = img.width
    height = img.height
    num_px = width * height
    # Write header
    plt = struct.pack('<8s2I2I', 'PLT V1  ', 10, 0, width, height)
    f.write(plt)

    # Search for layers containing plt data and save which plt layer
    # corresponds to which gimp layer
    # 1. Look for matching names
    plt_lay_ids = []
    for lay_id, lay in enumerate(img.layers):
        if lay.visible and lay.name.lower() in PLT_LAYERS:
            plt_lay_ids.append((PLT_LAYERS.index(lay.name.lower()), lay_id))
    # 2. Fallback: No layers haven been found
    #              Use the 10 top most layers instead
    if not plt_lay_ids:
        plt_lay_ids = [(lay_id, lay_id) for lay_id, lay in enumerate(img.layers)]
        
    num_layers = len(plt_lay_ids)  # For progress update in UI
    plt_px = [[255, 0] for _ in xrange(num_px)]
    
    # Generate image data from layers
    gimp.progress_init("Processing layers...")
    gimp.progress_update(0.0)
    
    # Create a temp image to handele resizing/cropping to image bounds 
    # (cheaper tto let gimp handle it)
    tmp_img = pdb.gimp_image_new(width, height, GRAY)
    tmp_img.disable_undo()
    for plt_id, lay_id in reversed(plt_lay_ids):
        # Copy layer and adjust its size to image bounds
        tmp_lay = pdb.gimp_layer_new_from_drawable(img.layers[lay_id], tmp_img)
        tmp_img.insert_layer(layer=tmp_lay, position=0)
        pdb.gimp_layer_resize_to_image_size(tmp_lay)
        # Extract pixel data
        region = tmp_lay.get_pixel_rgn(0, 0, width, height, False, False)
        lay_px = array('B', region[0:width, 0:height]) 
        bpp = region.bpp
        # Different way of getting data to account for missing alpha channel
        if tmp_lay.has_alpha:  # overwrite only if alpha value exceeds threshold
            plt_px = [([lay_px[i], plt_id] if lay_px[i+1] > LAYER_ALPHA_CUTOFF else plt_px[i/bpp]) 
                      for i in xrange(0, num_px*bpp, bpp)]
        else:  # overwrite everything
            plt_px = [[lay_px[i], plt_id] for i in xrange(0, num_px)]
        # Delete the tmp layer each time (not sure if gimp does it by itself)
        #pdb.gimp_item_delete(tmp_lay)
        # Progress update, layer by layer
        gimp.progress_update(float(plt_id+1)/float(num_layers))
          
    # Delete the temp image (not sure if gimp does it by itself)
    pdb.gimp_image_delete(tmp_img)

    # Progress update, done
    gimp.progress_update(1.0)

    # Adjust coordinates (gimp: top left origin => plt: bottom left origin)
    plt_px = [px for i in range(height) for px in
              plt_px[(height*width)-((i+1)*width):(height*width)-(i*width)]]
    plt_data = struct.pack('<' + str(num_px*2) + 'B',
                           *[i for sl in plt_px for i in sl])
    f.write(plt_data)
    f.close()


def plt_create_layers(img):
    
    def get_plt_pos(plt_id, layer_map):
        # Loop though preceeding plt_ids and check if they are present
        search_id = plt_id+1
        while search_id < len(PLT_LAYERS):
            if PLT_LAYERS[search_id] in layer_map:
                return layer_map[PLT_LAYERS[search_id]]+1
            search_id += 1
        return 0
    
    if not img:
        gimp.pdb.gimp_message('Invalid Image.')
        return
    
    # Get the type of layer from image type
    layer_type = GRAYA_IMAGE
    if img.base_type == RGB:
        layer_type = RGBA_IMAGE
    elif img.base_type == INDEXED:
        layer_type = INDEXEDA_IMAGE
        
    # Get all layers from the current image, mapped with its index
    layer_map = {lay.name:i for i, lay in enumerate(img.layers)}
    for plt_lay_id, plt_lay_name in enumerate(PLT_LAYERS):
        # We don't want to create already existing plt layers
        if plt_lay_name not in layer_map:
            # Insert at the correct position in case the layers exist partially
            lay_pos = get_plt_pos(plt_lay_id, layer_map)
            # Create an insert layer
            lay = gimp.Layer(img, plt_lay_name, img.width, img.height,
                             layer_type, 100, NORMAL_MODE)
            lay.fill(TRANSPARENT_FILL)
            img.insert_layer(layer=lay, position=lay_pos)


def register_load_handlers():
    gimp.register_load_handler('file-bioplt-load', 'plt', '')
    pdb['gimp-register-file-handler-mime']('file-bioplt-load', 'image/plt')
    # Too slow for python
    # pdb['gimp-register-thumbnail-loader']('file-bioplt-load',
    #                                       'file-bioplt-load-thumb')


def register_save_handlers():
    gimp.register_save_handler('file-bioplt-save', 'plt', '')
    pdb['gimp-register-file-handler-mime']('file-bioplt-save', 'image/plt')


register(
    'file-bioplt-load',  # name
    'load a Packed Layer Texture (.plt)',  # description
    'load a Packed Layer Texture (.plt)',
    'Attila Gyoerkoes',  # author
    'GPL v3',  # copyright
    '2015',  # year
    'Packed Layer Texture',
    None,  # image type
    [   # input args (type, name, description, default [, extra])
        (PF_STRING, 'filename', 'The name of the file to load', None),
        (PF_STRING, 'raw_filename', 'The name entered', None),
    ],
    [(PF_IMAGE, 'image', 'Output image')],  # results (type, name, description)
    plt_load,  # callback
    on_query=register_load_handlers,
    menu="<Load>",
)


register(
    'file-bioplt-save',
    'save a Packed Layer Texture (.plt)',
    'save a Packed Layer Texture (.plt)',
    'Attila Gyoerkoes',
    'GPL v3',
    '2015',
    'Packed Layer Texture',
    'RGB*, GRAY*',
    [   # input args (type, name, description, default [, extra])
        (PF_IMAGE, "image", "Input image", None),
        (PF_DRAWABLE, "drawable", "Input drawable", None),
        (PF_STRING, "filename", "The name of the file", None),
        (PF_STRING, "raw-filename", "The name of the file", None),
    ],
    [],
    plt_save,
    on_query=register_save_handlers,
    menu='<Save>'
)


register(
    'file-bioplt-createlayers',
    'Create Packed Layer Texture (.plt)',
    'Create the layers for a Packed Layer Texture (.plt)',
    'Attila Gyoerkoes',
    'GPL v3',
    '2015',
    'Plt: Setup Layers',
    '',
    [   # input args (type, name, description, default [, extra])
        (PF_IMAGE, "image", "Input image", None)
    ],
    [],
    plt_create_layers,
    menu='<Image>/Tools'
)


main()
