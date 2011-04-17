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
import java.util.ArrayList;

/**
 * Compressor for integer fingerprints, based on the PFOR-DELTA compression
 * algorithm.
 */
public class FingerprintCompressor {

    private ByteArrayOutputStream output = new ByteArrayOutputStream();
    private DataOutputStream dataOutput = new DataOutputStream(output);
    private ArrayList<Integer> bits = new ArrayList<Integer>();
    private int[] data;
    private int version;

    static final int MAX_NORMAL_VALUE = 7;
    static final int NORMAL_BITS = 3;
    static final int EXCEPTION_BITS = 5;
    
    public FingerprintCompressor(int[] fingerprint, int version) {
        data = fingerprint;
        this.version = version;
    }

    private void processSubfingerprint(int x) throws IOException {
        int bit = 1, lastBit = 0;
        while (x != 0) {
            if ((x & 1) != 0) {
                bits.add(bit - lastBit);
                lastBit = bit;
            }
            x >>>= 1;
            bit++;
        }
        bits.add(0);
    }

    private void writeNormalBits() throws IOException {
        BitStreamWriter writer = new BitStreamWriter(dataOutput);
        for (int x : bits) {
            writer.write(Math.min(x, MAX_NORMAL_VALUE), NORMAL_BITS);
        }
        writer.flush();
    }

    private void writeExceptionBits() throws IOException {
        BitStreamWriter writer = new BitStreamWriter(dataOutput);
        for (int x : bits) {
            if (x >= MAX_NORMAL_VALUE) {
                writer.write(x - MAX_NORMAL_VALUE, EXCEPTION_BITS);
            }
        }
        writer.flush();
    }

    public byte[] compress() throws IOException {
        dataOutput.writeInt(data.length | (version << 24));
        if (data.length > 0) {
            processSubfingerprint(data[0]);
            for (int i = 1; i < data.length; i++) {
                processSubfingerprint(data[i] ^ data[i - 1]);
            }
        }
        writeNormalBits();
        writeExceptionBits();
        return output.toByteArray();
    }

    public static byte[] compress(int[] fingerprint) throws IOException {
        return compress(fingerprint, 0);
    }

    public static byte[] compress(int[] fingerprint, int version) throws IOException {
        FingerprintCompressor compressor = new FingerprintCompressor(fingerprint, version);
        return compressor.compress();
    }

}
