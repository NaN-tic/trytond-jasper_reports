#!/bin/bash

if [ -z "$JAVA_HOME" ]; then
	directories="/usr/lib/jvm/java-7-openjdk-amd64/bin /usr/lib/j2sdk1.6-sun /usr/lib/j2sdk1.5-sun"
	for d in $directories; do
		if [ -d "$d" ]; then
			export JAVA_HOME="$d"
		fi
	done
fi

echo "JAVA_HOME=$JAVA_HOME"
export PATH="$JAVA_HOME"/bin:/bin:/usr/bin
export CLASSPATH=$(ls -1 lib/* | grep jar$ | awk '{printf "%s:", $1}')
export CLASSPATH="$CLASSPATH":$scriptdir

FILES=$(find com -iname "*.java")

echo "Compiling com.nantic.jasperreports.JasperServer"
javac -Xlint:deprecation $FILES || exit

rm -f lib/i18n.jar
rm -f i18n.jar
jar cvf i18n.jar com
mv i18n.jar lib

echo "Executing com.nantic.jasperreports.JasperServer"
java com.nantic.jasperreports.JasperServer
