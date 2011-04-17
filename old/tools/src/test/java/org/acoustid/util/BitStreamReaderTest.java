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

import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import junit.framework.TestCase;

public class BitStreamReaderTest extends TestCase {
    
    public BitStreamReaderTest(String testName) {
        super(testName);
    }

    public void testOneByte() throws IOException {
        byte[] data = { -28 };
        ByteArrayInputStream input = new ByteArrayInputStream(data);
        DataInputStream dataInput = new DataInputStream(input);

        BitStreamReader reader = new BitStreamReader(dataInput);
        assertEquals(0, reader.read(2));
        assertEquals(1, reader.read(2));
        assertEquals(2, reader.read(2));
        assertEquals(3, reader.read(2));
    }

    public void testTwoBytesIncomplete() throws IOException {
        byte[] data = { -28, 1 };
        ByteArrayInputStream input = new ByteArrayInputStream(data);
        DataInputStream dataInput = new DataInputStream(input);

        BitStreamReader reader = new BitStreamReader(dataInput);
        assertEquals(0, reader.read(2));
        assertEquals(1, reader.read(2));
        assertEquals(2, reader.read(2));
        assertEquals(3, reader.read(2));
        assertEquals(1, reader.read(2));
    }

    public void testTwoBytesSplit() throws IOException {
        byte[] data = { -120, 6 };
        ByteArrayInputStream input = new ByteArrayInputStream(data);
        DataInputStream dataInput = new DataInputStream(input);

        BitStreamReader reader = new BitStreamReader(dataInput);
        assertEquals(0, reader.read(3));
        assertEquals(1, reader.read(3));
        assertEquals(2, reader.read(3));
        assertEquals(3, reader.read(3));
    }

}
