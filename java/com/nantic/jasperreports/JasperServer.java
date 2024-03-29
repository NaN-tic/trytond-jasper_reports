package com.nantic.jasperreports;

import org.apache.xmlrpc.server.XmlRpcServer;
import org.apache.xmlrpc.webserver.WebServer;
//import org.apache.xmlrpc.webserver.*;
import org.apache.xmlrpc.*;
import org.apache.xmlrpc.server.PropertyHandlerMapping;
//import org.apache.xml.security.utils.Base64;

import net.sf.jasperreports.engine.JRRewindableDataSource;
import net.sf.jasperreports.engine.JRException;
import net.sf.jasperreports.engine.design.JRDesignField;
import net.sf.jasperreports.engine.util.JRLoader;
import net.sf.jasperreports.engine.JasperFillManager; 
import net.sf.jasperreports.engine.JasperExportManager;
import net.sf.jasperreports.engine.JasperCompileManager;
import net.sf.jasperreports.engine.JasperReport;
import net.sf.jasperreports.engine.JasperPrint;
import net.sf.jasperreports.engine.JRParameter;
import net.sf.jasperreports.engine.xml.JRXmlLoader;
import net.sf.jasperreports.engine.design.JasperDesign;
import net.sf.jasperreports.engine.data.JRXmlDataSource;
import net.sf.jasperreports.engine.data.JRCsvDataSource;
import net.sf.jasperreports.engine.JREmptyDataSource;

// Exporters
import net.sf.jasperreports.engine.JRAbstractExporter;
import net.sf.jasperreports.engine.export.HtmlExporter;
import net.sf.jasperreports.engine.export.JRPdfExporter;
import net.sf.jasperreports.engine.export.JRRtfExporter;
import net.sf.jasperreports.engine.export.JRCsvExporter;
import net.sf.jasperreports.engine.export.JRXlsExporter;
import net.sf.jasperreports.engine.export.JRTextExporter;
import net.sf.jasperreports.engine.export.oasis.JROdtExporter;
import net.sf.jasperreports.engine.export.oasis.JROdsExporter;
import net.sf.jasperreports.export.SimpleExporterInput;
import net.sf.jasperreports.export.SimpleHtmlExporterConfiguration;
import net.sf.jasperreports.export.SimpleOutputStreamExporterOutput;
import net.sf.jasperreports.export.SimpleTextReportConfiguration;
import net.sf.jasperreports.export.SimpleXlsReportConfiguration;

import java.text.NumberFormat;
import java.lang.Object;
import java.util.Date;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.Hashtable;
import java.util.ResourceBundle;
import java.util.Hashtable;
import java.io.ByteArrayInputStream;
import java.io.*;
import java.sql.*;
import java.lang.Class;
import java.math.BigDecimal;
import java.io.InputStream;
import java.util.Locale;



public class JasperServer { 
	/* Compiles the given .jrxml (inputFile) */
	public Boolean compile( String jrxmlPath ) throws java.lang.Exception {
		File jrxmlFile;
		File jasperFile;

		System.setProperty("jasper.reports.compiler.class", "com.nantic.jasperreports.I18nGroovyCompiler");

		jrxmlFile = new File( jrxmlPath );
		jasperFile = new File( jasperPath( jrxmlPath ) );
		if ( (! jasperFile.exists()) || (jrxmlFile.lastModified() > jasperFile.lastModified()) ) {
			System.out.println( "JasperServer: Compiling " + jrxmlPath ) ;
			JasperCompileManager.compileReportToFile( jrxmlPath, jasperPath( jrxmlPath ) );
			System.out.println( "JasperServer: Compiled.");
		}
		return true;
	}

	/* Returns path where bundle files are expected to be */
	public String bundlePath( String jrxmlPath ) {
		int index;
		index = jrxmlPath.lastIndexOf('.');
		if ( index != -1 )
			return jrxmlPath.substring( 0, index );
		else
			return jrxmlPath;
	}

	/* Returns the path to the .jasper file for the given .jrxml */
	public String jasperPath( String jrxmlPath ) {
		return bundlePath( jrxmlPath ) + ".jasper";
	}

	public int execute( Hashtable connectionParameters, String jrxmlPath, String outputPath, Hashtable parameters) throws java.lang.Exception {
		try {
			return privateExecute( connectionParameters, jrxmlPath, outputPath, parameters );
		} catch (Exception exception) {
			//exception.printStackTrace();
			throw exception;
		}
	}

	public int privateExecute( Hashtable connectionParameters, String jrxmlPath, String outputPath, Hashtable parameters) throws java.lang.Exception {

		JasperReport report = null;
		byte[] result = null;
		JasperPrint jasperPrint = null;
		InputStream in = null;
		int index;

		// Ensure report is compiled
		compile( jrxmlPath );

		report = (JasperReport) JRLoader.loadObjectFromFile(jasperPath(jrxmlPath));

		// Declare it outside the parameters loop because we'll use it when we will create the data source.
		Translator translator = null;

		// Fill in report parameters
		JRParameter[] reportParameters = report.getParameters();
		for( int j=0; j < reportParameters.length; j++ ){
			JRParameter jparam = reportParameters[j];	
			if ( jparam.getValueClassName().equals( "java.util.Locale" ) ) {
				// REPORT_LOCALE
				if ( ! parameters.containsKey( jparam.getName() ) )
					continue;
				String[] locales = ((String)parameters.get( jparam.getName() )).split( "_" );
				
				Locale locale;
				if ( locales.length == 1 )
					locale = new Locale( locales[0] );
				else
					locale = new Locale( locales[0], locales[1] );

				parameters.put( jparam.getName(), locale );

				// Initialize translation system
				// SQL reports will need to declare the TRANSLATOR paramter for translations to work.
				// CSV/XML based ones will not need that because we will integrate the translator 
				// with the CsvMultiLanguageDataSource.
				translator = new Translator( bundlePath(jrxmlPath), locale );
				parameters.put( "TRANSLATOR", translator );

			} else if( jparam.getValueClassName().equals( "java.lang.BigDecimal" )){
				Object param = parameters.get( jparam.getName());
				parameters.put( jparam.getName(), new BigDecimal( (Double) parameters.get(jparam.getName() ) ) );
			}
		}

		if ( connectionParameters.containsKey("subreports") ) {
			Object[] subreports = (Object[]) connectionParameters.get("subreports");
			for (int i = 0; i < subreports.length; i++ ) {
				Map m = (Map)subreports[i];

				// Ensure subreport is compiled
				String jrxmlFile = (String)m.get("jrxmlFile");
				if ( ! jrxmlFile.equals( "DATASET" ) )
					compile( (String)m.get("jrxmlFile") );

				// Create DataSource for subreport
				CsvMultiLanguageDataSource dataSource = new CsvMultiLanguageDataSource( (String)m.get("dataFile"), "utf-8", translator );
				System.out.println( "JasperServer: Adding parameter '" + ( (String)m.get("parameter") ) + "' with datasource '" + ( (String)m.get("dataFile") ) + "'" );

				parameters.put( m.get("parameter"), dataSource );
			}
		}
		String output;
		if ( connectionParameters.containsKey( "output" ) )
			output = (String)connectionParameters.get("output");
		else
			output = "pdf";

		if ( output.equalsIgnoreCase( "xls" ) )
			parameters.put( JRParameter.IS_IGNORE_PAGINATION, Boolean.TRUE );


		System.out.println( "JasperServer: Filling report..." );

		// Fill in report
		String language;
		if ( report.getQuery() == null )
			language = "";
		else
			language = report.getQuery().getLanguage();

		if( language.equalsIgnoreCase( "XPATH")  ){
			// If available, use a CSV file because it's faster to process.
			// Otherwise we'll use an XML file.
			if ( connectionParameters.containsKey("csv") ) {
				CsvMultiLanguageDataSource dataSource = new CsvMultiLanguageDataSource( (String)connectionParameters.get("csv"), "utf-8", translator );
				jasperPrint = JasperFillManager.fillReport( report, parameters, dataSource );
			} else {
				JRXmlDataSource dataSource = new JRXmlDataSource( (String)connectionParameters.get("xml"), "/data/record" );
				dataSource.setDatePattern( "yyyy-MM-dd HH:mm:ss" );
				dataSource.setNumberPattern( "#######0.##" );
				dataSource.setLocale( Locale.ENGLISH );
				jasperPrint = JasperFillManager.fillReport( report, parameters, dataSource );
			}
		} else if( language.equalsIgnoreCase( "SQL")  ) {
			Connection connection = getConnection( connectionParameters );
			jasperPrint = JasperFillManager.fillReport( report, parameters, connection );
		} else {
			JREmptyDataSource dataSource = new JREmptyDataSource();
			jasperPrint = JasperFillManager.fillReport( report, parameters, dataSource );
		}

		// Create output file
		File outputFile = new File( outputPath );
		JRAbstractExporter exporter;



		System.out.println( "JasperServer: Exporting..." );
		if ( output.equalsIgnoreCase( "html" ) ) {
			exporter = new HtmlExporter();
			// exporter.setParameter(JRHtmlExporterParameter.IS_USING_IMAGES_TO_ALIGN, Boolean.FALSE);
			// exporter.setParameter(JRHtmlExporterParameter.IS_REMOVE_EMPTY_SPACE_BETWEEN_ROWS, Boolean.TRUE);
            SimpleHtmlExporterConfiguration exporterConfiguration = new SimpleHtmlExporterConfiguration();
            exporterConfiguration.setHtmlHeader("");
            exporterConfiguration.setHtmlFooter("");
            exporterConfiguration.setBetweenPagesHtml("");
            exporter.setConfiguration(exporterConfiguration);
		} else if ( output.equalsIgnoreCase( "csv" ) ) {
			exporter = new JRCsvExporter();
		} else if ( output.equalsIgnoreCase( "xls" ) ) {
			exporter = new JRXlsExporter();
            SimpleXlsReportConfiguration exporterConfiguration = new SimpleXlsReportConfiguration();
            exporterConfiguration.setRemoveEmptySpaceBetweenColumns(Boolean.TRUE);
            exporterConfiguration.setRemoveEmptySpaceBetweenRows(Boolean.TRUE);
            exporterConfiguration.setDetectCellType(Boolean.TRUE);
            exporterConfiguration.setWhitePageBackground(Boolean.TRUE);
            exporterConfiguration.setMaxRowsPerSheet(65535);
            exporter.setConfiguration(exporterConfiguration);
		} else if ( output.equalsIgnoreCase( "rtf" ) ) {
			exporter = new JRRtfExporter();
		} else if ( output.equalsIgnoreCase( "odt" ) ) {
			exporter = new JROdtExporter();
		} else if ( output.equalsIgnoreCase( "ods" ) ) {
			exporter = new JROdsExporter();
		} else if ( output.equalsIgnoreCase( "txt" ) ) {
			exporter = new JRTextExporter();
            SimpleTextReportConfiguration exporterConfiguration = new SimpleTextReportConfiguration();
            exporterConfiguration.setPageWidthInChars(new Integer(80));
            exporterConfiguration.setPageHeightInChars(new Integer(150));
            exporter.setConfiguration(exporterConfiguration);
		} else {
			exporter = new JRPdfExporter();
		}
        exporter.setExporterInput(new SimpleExporterInput(jasperPrint));
		exporter.setExporterOutput(new SimpleOutputStreamExporterOutput(outputFile));
		exporter.exportReport();
		System.out.println( "JasperServer: Exported." );
		return jasperPrint.getPages().size(); 
	}

	public static Connection getConnection( Hashtable datasource ) throws java.lang.ClassNotFoundException, java.sql.SQLException { 
		Connection connection; 
		Class.forName("org.postgresql.Driver"); 
		connection = DriverManager.getConnection( (String)datasource.get("dsn"), (String)datasource.get("user"), 
		(String)datasource.get("password") ); 
		connection.setAutoCommit(true); 
		return connection; 
	}

	public static void main (String [] args) {
		try {
			int port = 8090;
			if ( args.length > 0 ) {
				port = java.lang.Integer.parseInt( args[0] );
			}
			java.net.InetAddress localhost = java.net.Inet4Address.getByName("localhost");
			System.out.println("JasperServer: Attempting to start XML-RPC Server at " + localhost.toString() + ":" + port + "...");
			WebServer server = new WebServer( port, localhost );
			XmlRpcServer xmlRpcServer = server.getXmlRpcServer();

			PropertyHandlerMapping phm = new PropertyHandlerMapping();
			phm.addHandler("Report", JasperServer.class);
			xmlRpcServer.setHandlerMapping(phm);

			server.start();
			System.out.println("JasperServer: Started successfully.");
			System.out.println("JasperServer: Accepting requests. (Halt program to stop.)");
		} catch (Exception exception) {
			System.err.println("Jasper Server: " + exception);
		}
	}
}
