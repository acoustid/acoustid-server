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

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import junit.framework.TestCase;
import org.apache.commons.lang.ArrayUtils;

public class BitStreamWriterTest extends TestCase {
    
    public BitStreamWriterTest(String testName) {
        super(testName);
    }

    public void testOneByte() throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        DataOutputStream dataOutput = new DataOutputStream(output);

        BitStreamWriter writer = new BitStreamWriter(dataOutput);
        writer.write(0, 2);
        writer.write(1, 2);
        writer.write(2, 2);
        writer.write(3, 2);
        writer.flush();

        byte[] expected = { -28 };
        assertEquals(ArrayUtils.toString(expected), ArrayUtils.toString(output.toByteArray()));
    }

    public void testTwoBytesIncomplete() throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        DataOutputStream dataOutput = new DataOutputStream(output);

        BitStreamWriter writer = new BitStreamWriter(dataOutput);
        writer.write(0, 2);
        writer.write(1, 2);
        writer.write(2, 2);
        writer.write(3, 2);
        writer.write(1, 2);
        writer.flush();

        byte[] expected = { -28, 1 };
        assertEquals(ArrayUtils.toString(expected), ArrayUtils.toString(output.toByteArray()));
    }

    public void testTwoBytesSplit() throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        DataOutputStream dataOutput = new DataOutputStream(output);

        BitStreamWriter writer = new BitStreamWriter(dataOutput);
        writer.write(0, 3);
        writer.write(1, 3);
        writer.write(2, 3);
        writer.write(3, 3);
        writer.flush();

        byte[] expected = { -120, 6 };
        assertEquals(ArrayUtils.toString(expected), ArrayUtils.toString(output.toByteArray()));
    }

}
