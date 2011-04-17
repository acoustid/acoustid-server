/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */

package org.acoustid.server.handler;

public class BadRequestException extends HandlerException {

    /**
     * Creates a new instance of <code>BadRequestException</code> without detail message.
     */
    public BadRequestException() {
    }

    /**
     * Constructs an instance of <code>BadRequestException</code> with the specified detail message.
     * @param msg the detail message.
     */
    public BadRequestException(String msg) {
        super(msg);
    }

    /**
     * Constructs an instance of <code>BadRequestException</code> with the specified detail message and cause.
     * @param msg the detail message.
     * @param cause the cause.
     */
    public BadRequestException(String msg, Throwable cause) {
        super(msg, cause);
    }

}
