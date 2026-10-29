public class newV {
    // difference taken the other way, zero included in the flip (-0 is 0), negation written as 0 - d
    public static double snippet(int a, int b) {
        int d = 0;
        d = b - a;
        if (d <= 0) {
            d = 0 - d;
        }
        return d;
    }
}
