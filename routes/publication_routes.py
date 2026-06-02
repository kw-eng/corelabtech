#Research
#├ Publications
#├ Datasets
#└ Reports
from flask import Blueprint, render_template
import os

pub_bp = Blueprint("pub", __name__)

@pub_bp.route("/publications")
def publications():

 files = os.listdir("research/papers")

 return render_template(
"publications.html",
  papers=files
)

@pub_bp.route("/research/datasets")
def datasets():
 return render_template("datasets.html")

@pub_bp.route("/research/reports")
def reports():
 return render_template("reports.html")
