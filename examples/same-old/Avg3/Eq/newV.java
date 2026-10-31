public class newV {
    // split the sum into whole sixes and the rest: 2 per six, plus the rest divided by 3 (both round toward zero the same way)
    public static double snippet(int a, int b, int c) {
        int avg = 0;
        int s = 0;
        s = a + b + c;
        avg = s / 6 * 2 + (s - s / 6 * 6) / 3;
        return avg;
    }
}
