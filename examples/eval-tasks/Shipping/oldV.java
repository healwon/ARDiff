public class oldV {
    public static double snippet(int weight, int total, int express) {
        int fee = 0;
        int extra = 0;
        fee = 5;
        if (weight > 10) {
            extra = (weight - 10) / 2;
        }
        fee = fee + extra;
        if (total >= 100) {
            fee = 0;
        }
        return fee;
    }
}
