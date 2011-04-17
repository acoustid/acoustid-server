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

package org.acoustid.server.util;

public class MissingParameterException extends Exception {

	private static final long serialVersionUID = 4707680957916961581L;

	/**
     * Creates a new instance of <code>MissingParameterException</code> without detail message.
     */
    public MissingParameterException() {
    }


    /**
     * Constructs an instance of <code>MissingParameterException</code> with the specified detail message.
     * @param msg the detail message.
     */
    public MissingParameterException(String msg) {
        super(msg);
    }

}
