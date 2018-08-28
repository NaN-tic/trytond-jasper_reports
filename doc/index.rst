Adds support for using JasperReports-based reports.

Note that the module creates a Java process which listens on localhost
for XML-RPC calls to avoid the overhead of loading the java virtual machine
each time a report is called.

Given that filenames are given tot the Java process, this could be a security
issue if you cannot rely on the users who can stablish TCP/IP connections
to localhost.
