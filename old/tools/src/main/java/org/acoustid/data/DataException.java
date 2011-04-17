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

package org.acoustid.data;

public class DataException extends Exception {

    /**
     * Creates a new instance of <code>DataException</code> without detail message.
     */
    public DataException() {
    }


    /**
     * Constructs an instance of <code>DataException</code> with the specified detail message.
     * @param msg the detail message.
     */
    public DataException(String msg) {
        super(msg);
    }


    /**
     * Constructs an instance of <code>DataException</code> with the specified detail message and cause.
     * @param msg the detail message.
     * @param cause the cause.
     */
    public DataException(String msg, Throwable cause) {
        super(msg, cause);
    }

    /**
     * Constructs an instance of <code>DataException</code> with the specified cause.
     * @param cause the cause.
     */
    public DataException(Throwable cause) {
        super(cause);
    }

}
