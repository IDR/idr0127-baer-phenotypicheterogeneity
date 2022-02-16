import argparse
import sys
import csv
import logging
import math
import omero
import omero.cli
from omero.model.enums import UnitsLength
from omero.gateway import BlitzGateway
from omero.rtypes import rdouble, rstring, rint
import os.path
from collections import defaultdict
import re

# Generate circle/ellipse ROIs from the csv files.
# Run it like this:
# find /uod/idr/metadata/idr0127-baer-phenotypicheterogeneity/FeatureLevelData -type f -exec python process_rois.py [PROJECT_ID] {} \;

log = logging.getLogger()

def read_csv(filename, frame=-1):
    coords = defaultdict(list)
    pixelsize = None
    with open(filename, mode='r') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        rows = list(csv_reader)
        for r in rows:
            if frame !=-1 and frame == r['Frame']:
                coords[r['Colony']].append(
                    (r['Frame'],r['X_centerPx'],r['Y_centerPx'],r['RadiusPx']))
            if pixelsize is None:
                pixelsize = float(r['Spatial_calibration'])
            else:
                if math.isnan(r['Spatial_calibration']):
                    assert math.isnan(pixelsize)
                else:
                    assert pixelsize == float(r['Spatial_calibration'])
    return coords, pixelsize


def create_roi(colony, coords):
    roi = omero.model.RoiI()
    for t, x, y, r in coords:
        if r == "NaN":
            sh = omero.model.PointI()
            sh.y = rdouble(x)
            sh.x = rdouble(y)
            sh.theZ = rint(0)
            sh.theT = rint(int(t)-1)
            sh.textValue = rstring(colony)
            roi.addShape(sh)
        else:
            sh = omero.model.EllipseI()
            sh.y = rdouble(y)
            sh.x = rdouble(x)
            sh.radiusX = rdouble(r)
            sh.radiusY = rdouble(r)
            sh.theZ = rint(0)
            sh.theT = rint(int(t)-1)
            sh.textValue = rstring(colony)
            roi.addShape(sh)
    return roi


def save_roi(conn, img, roi):
    us = conn.getUpdateService()
    im = conn.getObject('Image', img.id)
    roi.setImage(im._obj)
    us.saveAndReturnObject(roi)
    log.info(f"Saved Roi for {img.getName()}")


def save_pixel_size(conn, img, pixelsize):
    us = conn.getUpdateService()
    size = omero.model.LengthI(pixelsize, UnitsLength.MICROMETER)
    im = conn.getObject('Image', img.id)
    p = im.getPrimaryPixels()._obj
    p.setPhysicalSizeX(size)
    p.setPhysicalSizeY(size)
    us.saveObject(p)
    log.info(f"Saved physical size for {im.getName()}")


def delete_rois(conn, im):
    result = conn.getRoiService().findByImage(im.id, None)
    to_delete = []
    for roi in result.rois:
        to_delete.append(roi.getId().getValue())
    if to_delete:
        log.info(f"Deleting existing {len(to_delete)} rois on image {im.name}.")
        conn.deleteObjects("Roi", to_delete, deleteChildren=True, wait=True)


def populate_experiment(conn, experiment, dry_run=True):
    currentdir = os.path.dirname(sys.argv[0])

    project_name = f"idr0127-baer-phenotypicheterogeneity/{experiment}"
    project = conn.getObject('Project', attributes={'name': project_name})
    for dataset in project.listChildren():
        for image in dataset.listChildren():
            if not dry_run:
                delete_rois(conn, image)
            originalpath = image.getImportedImageFilePaths()['client_paths'][0]
            log.debug(f"Looking for CSV associated with {originalpath}")
            csv_file = os.path.basename(
                originalpath.replace(".ome.tiff", ".csv"))
            # Frames of images are split into separate images
            frame = -1
            if experiment == "experimentB":
                frame = image.getName()[-2:]
                csv_file = csv_file.replace(f"_Image{frame}", "")
            csv_path = os.path.join(
                currentdir, "..", experiment, "features", csv_file)
            if not os.path.exists(csv_path):
                log.error(f"{csv_path} does not exist")
            coords, pixelsize = read_csv(csv_path, frame=int(frame))

            if not math.isnan(pixelsize):
                save_pixel_size(conn, image, pixelsize)

            for colony, coords in coords.items():
                roi = create_roi(colony, coords)
                if not dry_run:
                    save_roi(conn, image, roi)

def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--verbose', '-v', action='count', default=0,
        help='Increase the command verbosity')
    parser.add_argument(
        '--quiet', '-q', action='count', default=0,
        help='Decrease the command verbosity')
    parser.add_argument(
        '--dry-run', '-n', action='store_true',
        help='Run command in dry-run mode')
    args = parser.parse_args(argv)


    default_level = logging.INFO - 10 * args.verbose + 10 * args.quiet
    logging.basicConfig(level=default_level)

    with omero.cli.cli_login() as c:
        conn = omero.gateway.BlitzGateway(client_obj=c.get_client())
        currentdir = os.path.dirname(sys.argv[0])
        for experiment in ["experimentA", "experimentB", "experimentC"]:
            populate_experiment(conn, experiment, dry_run=args.dry_run)


if __name__ == "__main__":
    main(sys.argv[1:])
