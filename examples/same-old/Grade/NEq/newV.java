public class newV {
    // "tidied" top bound: 90 itself now gets 1
    public static double snippet(int score) {
        int g = 0;
        if (score >= 60) {
            g = 1;
        }
        if (score > 90) {
            g = 2;
        }
        return g;
    }
}
