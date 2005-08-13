from wxPython.wx import wxPlatform

if wxPlatform == '__WXMSW__':
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
