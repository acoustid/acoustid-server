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

package org.acoustid.util;

import java.io.DataOutputStream;
import java.io.IOException;

public class BitStreamWriter {

    private DataOutputStream out;
    private int buffer = 0;
    private int bufferSize = 0;

    public BitStreamWriter(DataOutputStream out) {
        this.out = out;
    }

    public void write(int value, int numBits) throws IOException {
        buffer |= value << bufferSize;
        bufferSize += numBits;
        while (bufferSize >= 8) {
            out.writeByte(buffer & 255);
            buffer >>= 8;
            bufferSize -= 8;
        }
    }

    public void flush() throws IOException {
        while (bufferSize > 0) {
            out.writeByte(buffer & 255);
            buffer >>= 8;
            bufferSize -= 8;
        }
        buffer = 0;
        bufferSize = 0;
    }

}
