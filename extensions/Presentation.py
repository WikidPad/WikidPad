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


if Platform == '__WXMSW__':
    INTHTML_FONTSIZES = (7, 8, 10, 12, 16, 22, 30)

elif Platform == '__WXMAC__':
    INTHTML_FONTSIZES = (9, 12, 14, 18, 24, 30, 36)

else:
    INTHTML_FONTSIZES = (10, 12, 14, 16, 19, 24, 32)


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
