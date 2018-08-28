===============
Informes Jasper
===============

Añade funcionalidad para soportar el uso de informes basados en Jasper.

El módulo crea un proceso Java que escucha llamadas XML-RPC en
localhost para evitar la sobrecarga de la máquina virtual de java
cada vez que se envía un informe.

Teniendo en cuenta que se envía el nombre del archivo al proceso
Java, esto podría ser un problema de seguridad si no se puede confiar
en los usuarios que pueden establecer conexiones TCP/IP con
localhost.

En el parámetro **fonts_path** del apartado **jasper** del fichero de
configuración del *trytond* se puede especificar una lista separada por comas
de rutas a ficheros *.jar* o a directorios que contienen ficheros *.jar*
generados desde *iReport* que contengan definiciones de fuentes que se usarán
en los informes.

Para generar estos ficheros *.jar* hay que ir al menú **Tools / Options** e
instalar la fuente True Type en la pestaña **Fonts**. Importante marcar la
opción **PDF Embeded**. Luego, se genera el fichero *.jar* con el botón
**Export as extension**.
