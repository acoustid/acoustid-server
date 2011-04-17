// Acoustid -- Audio fingerprint lookup server
// Copyright (C) 2010  Lukas Lalinsky
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

package org.acoustid.server.handler.ws;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import javax.xml.stream.XMLOutputFactory;
import javax.xml.stream.XMLStreamException;
import org.acoustid.server.handler.BadRequestException;
import org.acoustid.server.handler.RequestHandler;
import org.acoustid.server.util.MissingParameterException;
import org.acoustid.server.util.ParameterFormatException;
import org.acoustid.server.util.ParameterMap;
import org.acoustid.server.util.SimpleXMLStreamWriter;
import org.apache.log4j.Logger;

public abstract class WebServiceRequestHandler implements RequestHandler {

    private static final Logger logger = Logger.getLogger(WebServiceRequestHandler.class);

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response) throws Exception {
        ParameterMap params = null;
        try {
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            SimpleXMLStreamWriter writer = new SimpleXMLStreamWriter(XMLOutputFactory.newInstance().createXMLStreamWriter(output));
            params = ParameterMap.parseRequest(request);
            handleWebServiceRequest(writer, params);
            sendResponse(response, output.toByteArray());
        }
        catch (MissingParameterException ex) {
            logger.error("Error", ex);
            if (params != null) {
                logger.warn(params);
            }
            sendErrorResponse(response, ex.getMessage(), HttpServletResponse.SC_BAD_REQUEST);
        }
        catch (ParameterFormatException ex) {
            logger.error("Error", ex);
            if (params != null) {
                logger.warn(params);
            }
            sendErrorResponse(response, ex.getMessage(), HttpServletResponse.SC_BAD_REQUEST);
        }
        catch (BadRequestException ex) {
            logger.error("Error", ex);
            if (params != null) {
                logger.warn(params);
            }
            sendErrorResponse(response, ex.getMessage(), HttpServletResponse.SC_BAD_REQUEST);
        }
        catch (Exception ex) {
            logger.error("Error", ex);
            if (params != null) {
                logger.warn(params);
            }
            sendErrorResponse(response, ex.getMessage(), HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
        }
    }

    protected void sendResponse(HttpServletResponse response, byte[] content) throws IOException {
        sendResponse(response, content, HttpServletResponse.SC_OK);
    }

    protected void sendResponse(HttpServletResponse response, byte[] content, int status) throws IOException {
        response.setContentType("text/xml");
        response.setCharacterEncoding("UTF-8");
        response.getOutputStream().write(content);
        response.setStatus(status);
    }

    protected void sendErrorResponse(HttpServletResponse response, String message, int status) throws IOException, XMLStreamException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        SimpleXMLStreamWriter writer = new SimpleXMLStreamWriter(XMLOutputFactory.newInstance().createXMLStreamWriter(output));
        writer.writeStartDocument("UTF-8", "1.0");
        writer.writeStartElement("response");
        writer.writeAttribute("status", "error");
        writer.writeTextElement("error", message);
        writer.writeEndElement();
        writer.writeEndDocument();
        sendResponse(response, output.toByteArray(), status);
    }

    public abstract void handleWebServiceRequest(SimpleXMLStreamWriter writer, ParameterMap params) throws Exception;

}
