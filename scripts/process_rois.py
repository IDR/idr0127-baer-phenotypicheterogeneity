import sys
import csv
import omero
import omero.cli
from omero.gateway import BlitzGateway
from omero.rtypes import rdouble, rstring, rint
from collections import defaultdict
import re

# Generate circle/ellipse ROIs from the csv files.
# Run it like this:
# find /uod/idr/metadata/idr0127-baer-phenotypicheterogeneity/FeatureLevelData/1_Patient_TL -type f -exec python process_rois.py 2251
# find /uod/idr/metadata/idr0127-baer-phenotypicheterogeneity/FeatureLevelData/2_Patient_EP -type f -exec python process_rois.py 2251
# find /uod/idr/metadata/idr0127-baer-phenotypicheterogeneity/FeatureLevelData/3_Exponential_TL -type f -exec python process_rois.py 2251

if len(sys.argv) < 2:
    print("Usage: python process_rois.py [PROJECT_ID] [CSV_FILE]")
    exit(1)


filename = sys.argv[2]

imagename = re.search(".+/(?P<basename>.+)\.csv", filename).group('basename') + ".ome.tiff"
projectid = int(sys.argv[1])


def read_csv():
    coords = defaultdict(list)
    with open(filename, mode='r') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        rows = list(csv_reader)
        for r in rows:
            coords[r['Colony']].append((r['Frame'],r['X_centerPx'],r['Y_centerPx'],r['RadiusPx']))
    return coords


def load_image(conn):
    # for dataset one and three
    project = conn.getObject('Project', attributes={'id': projectid})
    for dataset in project.listChildren():
        for image in dataset.listChildren():
            if image.getName() == imagename:
                return image
    print(f"Could not find image {imagename}")
    exit(1)


def load_image_2(conn):
    # for the second dataset only
    images = []
    project = conn.getObject('Project', attributes={'id': projectid})
    for dataset in project.listChildren():
        for image in dataset.listChildren():
            if imagename.replace(".ome.tiff", "") in image.getName():
                images.append(image)
    if not images:
        print(f"Could not find the images for {imagename}")
        exit(1)
    return images


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
    print(f"Saved Roi for {img.getName()}")


def delete_rois(conn, im):
    result = conn.getRoiService().findByImage(im.id, None)
    to_delete = []
    for roi in result.rois:
        to_delete.append(roi.getId().getValue())
    if to_delete:
        print(f"Deleting existing {len(to_delete)} rois on image {im.name}.")
        conn.deleteObjects("Roi", to_delete, deleteChildren=True, wait=True)


with omero.cli.cli_login() as c:
    conn = omero.gateway.BlitzGateway(client_obj=c.get_client())
    coords = read_csv()
    if len(coords[list(coords.keys())[0]]) > 4:
        # dataset one and three
        image = load_image(conn)
        delete_rois(conn, image)
        for colony, coords in coords.items():
            roi = create_roi(colony, coords)
            save_roi(conn, image, roi)
    else:
        # dataset two
        images = load_image_2(conn)
        for i in images:
            delete_rois(conn, i)
        for colony, coords in coords.items():
            image = None
            for t, x, y, r in coords:
                for img in images:
                    if f"Image0{t}" in img.getName():
                        image = img
                roi = create_roi(colony, [(0, x, y, r)])
                save_roi(conn, image, roi)
