import sqlite3
import matplotlib.pyplot as plt # type: ignore
from reportlab.platypus import SimpleDocTemplate,Paragraph,Image
from reportlab.lib.styles import getSampleStyleSheet

def generate_report():

 con=sqlite3.connect("data/database.db")

 c=con.cursor()

 c.execute("""
SELECT timestamp, spo2, pulse, hrv, pressure_ata
FROM tests
ORDER BY timestamp DESC
""")

 rows=c.fetchall()

 dates=[r[0] for r in rows]

 spo2=[r[1] for r in rows]

 plt.plot(dates,spo2)

 plt.title("SpO2 over time")

 chart="static/chart.png"

 plt.savefig(chart)

 styles=getSampleStyleSheet()

 story=[]

 story.append(Paragraph("CoreLabTech Research Report",styles["Title"]))

 story.append(Image(chart))

 pdf="research/report.pdf"

 doc=SimpleDocTemplate(pdf)

 doc.build(story)

 return pdf