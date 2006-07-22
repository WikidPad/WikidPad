import sys, traceback, time, os.path

# global exception control
class StdErrReplacement:
    def write(self, data):
        import ExceptionLogger as EL
#         global _exceptionDestDir, _exceptionSessionTimeStamp, _exceptionOccurred
#         global _previousExcepthook

        try:
            f = open(os.path.join(EL._exceptionDestDir, "WikidPad_Error.log"), "a")
            try:
                if not EL._timestampPrinted:
                    # (Only write for first exception in session) This isn't an exception
                    f.write(EL._exceptionSessionTimeStamp)
                    EL._timestampPrinted = True
                sys.stdout.write(data)
                f.write(data)
            finally:
                f.close()
        except:
            pass # TODO

    def writelines(self, it):
        for l in it:
            self.write(l)
            
#     def __getattr__(self, attr):
#         print "__getattr__", repr(attr)
#         return None


# class ExceptionHandler:
#     def __init__(self):
#         global _exceptionDestDir, _exceptionSessionTimeStamp, _exceptionOccurred
#         global _previousExcepthook
#         self._exceptionDestDir = _exceptionDestDir
#         self._exceptionSessionTimeStamp = _exceptionSessionTimeStamp
#         self._exceptionOccurred = _exceptionOccurred
#         self._previousExcepthook = _previousExcepthook
#         self.traceback = traceback
# 

def onException(typ, value, trace):
#     global _exceptionDestDir, _exceptionSessionTimeStamp, _exceptionOccurred
#     global _previousExcepthook
#     global _traceback2
    import ExceptionLogger as EL

    try:
##        traceback.print_exception(typ, value, trace, file=sys.stdout)
        f = open(os.path.join(EL._exceptionDestDir, "WikidPad_Error.log"), "a")
        try:
            if not EL._timestampPrinted:
                # Only write for first exception in session
                f.write(EL._exceptionSessionTimeStamp)
                EL._timestampPrinted = True
            
            EL._exceptionOccurred = True
            EL.traceback.print_exception(typ, value, trace, file=f)
            EL.traceback.print_exception(typ, value, trace, file=sys.stdout)
        finally:
            f.close()
    except:
        print "Exception occurred during global exception handling:"
        EL.traceback.print_exc(file=sys.stdout)
        print "Original exception:"
        EL.traceback.print_exception(typ, value, trace, file=sys.stdout)
        EL._previousExcepthook(typ, value, trace)


def startLogger(versionstring):
    import ExceptionLogger as EL
    
    EL._exceptionDestDir = os.path.dirname(os.path.abspath(sys.argv[0]))
    EL._exceptionSessionTimeStamp = \
            time.strftime("\n\nVersion: '" + versionstring +
                    "' Session start: %Y-%m-%d %H:%M:%S\n")
    EL._exceptionOccurred = False
    EL._timestampPrinted = False
    
    
    EL._previousExcepthook = sys.excepthook
    sys.excepthook = onException
    
    EL._previousStdErr = sys.stderr
    sys.stderr = StdErrReplacement()

