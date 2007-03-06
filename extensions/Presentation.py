from wx import Platform

if Platform == '__WXMSW__':
    faces = { 'times': 'Times New Roman',
              'mono' : 'Courier New',
              'helv' : 'Arial',
              'other': 'Comic Sans MS',
              'size' : 10,
              'heading4': 10,
              'heading3': 11,
              'heading2': 12,
              'heading1': 12
             }
else:
    faces = { 'times': 'Times',
              'mono' : 'Courier',
              'helv' : 'Helvetica',
              'other': 'new century schoolbook',
              'size' : 10,
              'heading4': 10,
              'heading3': 11,
              'heading2': 12,
              'heading1': 12
             }


# Original settings:
"""
if Platform == '__WXMSW__':
    faces = { 'times': 'Times New Roman',
              'mono' : 'Courier New',
              'helv' : 'Arial',
              'other': 'Comic Sans MS',
              'size' : 10,
              'heading4': 11,
              'heading3': 12,
              'heading2': 13,
              'heading1': 14
             }
else:
    faces = { 'times': 'Times',
              'mono' : 'Courier',
              'helv' : 'Helvetica',
              'other': 'new century schoolbook',
              'size' : 10,
              'heading4': 11,
              'heading3': 12,
              'heading2': 13,
              'heading1': 14
             }
"""
