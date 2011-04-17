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

package org.acoustid.server;

public class Chromaprint {

    private static final int FFT_FRAME_SIZE = 4096;
    private static final int SAMPLE_RATE = 11025;
    private static final int OVERLAP = 3;
    private static final double STEP_LENGTH = (double)FFT_FRAME_SIZE / SAMPLE_RATE / OVERLAP;
    private static final int WINDOW_SIZE = 16;

    public static final int FINGERPRINT_VERSION = 1;

    /**
     * Estimate the size of a Chromaprint fingerprint, based on the audio length
     * in seconds.
     * 
     * @param length length of the audio stream in seconds
     * @return number of items the fingerprint should contain
     */
    public static int estimateFingerprintSize(int length) {
        return (int)(length / STEP_LENGTH) - WINDOW_SIZE;
    }

    /**
     * Check whether audio of the specified length could generate a fingerprint
     * of the specified size.
     *
     * @param length length of the audio stream in seconds
     * @param size number of items in the fingerprint
     * @return whether the fingerprint size is realistic
     */
    public static boolean isGoodFingerprintSize(int length, int size) {
        int expectedSize = estimateFingerprintSize(length);
        return Math.abs(size - expectedSize) < WINDOW_SIZE;
    }

};

