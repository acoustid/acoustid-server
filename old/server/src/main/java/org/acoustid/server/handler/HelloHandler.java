/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */

package org.acoustid.server.handler;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

public class HelloHandler implements RequestHandler {

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response) throws Exception {
        response.setContentType("text/plain");
        response.setCharacterEncoding("UTF-8");
        response.getWriter().println("hello");
        response.setStatus(HttpServletResponse.SC_OK);
    }

}
